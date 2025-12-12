# monitor_agent.py

import uuid
import os
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
import shutil

from agent_adk import AgentADK
from src.core.protocol import AgentResponse
from src.core.logger import logger


def scan_directory_tool(directory_path: str) -> Dict[str, Any]:
    watch_dir = Path(directory_path)
    jobs = []
    
    try:
        if not watch_dir.exists():
            return {"files_found": [], "error": "Directory does not exist"}
        
        for file_path in watch_dir.glob("*.*"):
            if file_path.name.startswith(".") or file_path.name.endswith(".meta.json"):
                continue
            jobs.append(str(file_path))
        
        return {"files_found": jobs, "count": len(jobs)}
    except Exception as e:
        return {"files_found": [], "error": str(e)}


class InvoiceMonitorAgent(AgentADK):
    
    def __init__(
        self, 
        watch_dir: str = "data/invoices", 
        processed_dir: str = "data/processed",
        model: str = "bedrock/amazon.nova-lite-v1:0"
    ):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        instruction = f"""You are a System Watchdog responsible for monitoring invoice files.

Your tasks:
1. Use the scan_directory_tool to check for new files in: {watch_dir}
2. Report the number of files found
3. Identify if any files need processing
4. Provide a brief status update

When scanning, call scan_directory_tool with the directory path as parameter.

Respond with:
- Number of files detected
- Status: "files_pending" or "no_files"
- Brief summary of what was found"""
        
        tools = None if "cohere" in model.lower() else [scan_directory_tool]
        
        super().__init__(
            name="Invoice_Monitor_Agent",
            instruction=instruction,
            model=model,
            tools=tools,
            verbose=True
        )
        
        self._watch_dir_str = str(self.watch_dir)
    
    def scan(self) -> List[Dict]:
        jobs = []
        
        try:
            for file_path in self.watch_dir.glob("*.*"):
                if file_path.name.startswith(".") or file_path.name.endswith(".meta.json"):
                    continue
                
                jobs.append({
                    "file_path": str(file_path),
                    "timestamp": file_path.stat().st_mtime,
                    "metadata": {}
                })
            
            return sorted(jobs, key=lambda x: x["timestamp"])
        
        except Exception as e:
            logger.error(f"Error scanning directory: {e}")
            return []
    
    def archive(self, file_path_str: str, dest_name: str = None):
        source_path = Path(file_path_str)
        
        if not source_path.exists():
            logger.warning(f"File not found for archiving: {source_path}")
            return
        
        if not dest_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_name = f"{timestamp}_{source_path.name}"
        
        dest_path = self.processed_dir / dest_name
        
        try:
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Archived file: {source_path.name} -> {dest_path}")
            
            meta_source = source_path.with_suffix(source_path.suffix).parent / f"{source_path.stem}.meta.json"
            if meta_source.exists():
                meta_dest_name = f"{Path(dest_name).stem}.meta.json"
                meta_dest = self.processed_dir / meta_dest_name
                shutil.move(str(meta_source), str(meta_dest))
                logger.info(f"Archived metadata: {meta_source.name} -> {meta_dest}")
        
        except Exception as e:
            logger.error(f"Failed to archive {source_path.name}: {e}")
    
    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        context_id = inputs.get("context_id", None)
        
        jobs = self.scan()
        
        agent_thought = ""
        if self.tools:
            try:
                await self.setup_session()
                prompt = f"Please scan the directory '{self._watch_dir_str}' and report status."
                agent_thought = await self.process_message(prompt)
                await self.cleanup()
            except Exception as e:
                logger.warning(f"Agent processing failed, using direct scan: {e}")
                agent_thought = f"Direct scan: {len(jobs)} files found"
        else:
            agent_thought = f"Direct scan completed: {len(jobs)} files detected"
        
        if not jobs:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent="Invoice Monitor Agent",
                target_agent="Orchestrator",
                message_type="STATUS",
                payload={
                    "status": "idle",
                    "files_found": 0,
                    "agent_thought": agent_thought
                },
                context_id=context_id
            )
        
        target = jobs[0]
        file_path = Path(target["file_path"])
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent="Invoice Monitor Agent",
            target_agent="Extractor Agent",
            message_type="TASK_HANDOFF",
            payload={
                "file_path": target["file_path"],
                "file_name": file_path.name,
                "timestamp": datetime.now().isoformat(),
                "status": "detected",
                "metadata": target.get("metadata", {}),
                "total_pending": len(jobs),
                "agent_thought": agent_thought
            },
            context_id=f"ctx_{file_path.stem}_{uuid.uuid4().hex[:8]}"
        )
    
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))
    
    def get_pending_count(self) -> int:
        return len(self.scan())
    
    def clear_watch_directory(self):
        jobs = self.scan()
        for job in jobs:
            self.archive(job["file_path"])
        logger.info(f"Cleared {len(jobs)} files from watch directory")


if __name__ == "__main__":
    import asyncio
    from pathlib import Path
    
    async def test_agent_with_real_directory():
        watch_dir = Path("data/invoices")
        processed_dir = Path("data/processed")
        
        watch_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        agent = InvoiceMonitorAgent(
            watch_dir=str(watch_dir),
            processed_dir=str(processed_dir),
            model="bedrock/amazon.nova-lite-v1:0"
        )
        
        agent.print_info()
        
        print("\n" + "="*70)
        print("INVOICE MONITOR AGENT - REAL DIRECTORY TEST")
        print("="*70 + "\n")
        
        print(f"Watching: {watch_dir.absolute()}")
        print(f"Archiving to: {processed_dir.absolute()}\n")
        
        print("="*70)
        print("TEST 1: Current Directory State")
        print("="*70)
        jobs = agent.scan()
        print(f"Files currently in watch directory: {len(jobs)}")
        if jobs:
            print("\nFiles found:")
            for i, job in enumerate(jobs, 1):
                file_path = Path(job['file_path'])
                file_size = file_path.stat().st_size / 1024
                modified = datetime.fromtimestamp(job['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {i}. {file_path.name}")
                print(f"     Size: {file_size:.2f} KB | Modified: {modified}")
        else:
            print("  No files found in watch directory")
            print(f"  Please add invoice files to: {watch_dir.absolute()}")
        print()
        
        print("="*70)
        print("TEST 2: Agent File Detection")
        print("="*70)
        response = await agent.process_async({})
        print(f"Message Type: {response.message_type}")
        print(f"Source Agent: {response.source_agent}")
        print(f"Target Agent: {response.target_agent}")
        print(f"Status: {response.payload.get('status', 'N/A')}")
        print(f"Files Pending: {response.payload.get('total_pending', 0)}")
        
        if response.payload.get('file_name'):
            print(f"\nNext File to Process:")
            print(f"   Name: {response.payload['file_name']}")
            print(f"   Path: {response.payload['file_path']}")
            print(f"   Context ID: {response.context_id}")
        
        if response.payload.get('agent_thought'):
            print(f"\nAgent Analysis:")
            print(f"   {response.payload['agent_thought']}")
        print()
        
        if response.payload.get('file_path'):
            print("="*70)
            print("TEST 3: Archive Functionality")
            print("="*70)
            file_to_archive = response.payload['file_path']
            file_name = response.payload['file_name']
            
            print(f"\nFound file: {file_name}")
            user_input = input("Do you want to archive this file? (yes/no): ").strip().lower()
            
            if user_input in ['yes', 'y']:
                agent.archive(file_to_archive)
                print(f"Archived: {file_name}")
                
                archived_path = processed_dir / f"{datetime.now().strftime('%Y%m%d')}*{file_name}"
                print(f"   Location: {processed_dir.absolute()}")
                
                jobs_after = agent.scan()
                print(f"   Files remaining in watch directory: {len(jobs_after)}")
            else:
                print("Skipped archiving")
        print()
        
        print("="*70)
        print("TEST 4: Monitoring Loop Simulation (3 iterations)")
        print("="*70)
        for iteration in range(1, 4):
            print(f"\nIteration {iteration}:")
            count = agent.get_pending_count()
            print(f"   Pending files: {count}")
            
            if count > 0:
                response = await agent.process_async({})
                if response.message_type == "TASK_HANDOFF":
                    print(f"   Detected: {response.payload['file_name']}")
                else:
                    print(f"   Status: {response.payload.get('status', 'unknown')}")
            else:
                print("   No files to process")
            
            await asyncio.sleep(1)
        print()
        
        print("="*70)
        print("TEST 5: Final Summary")
        print("="*70)
        final_jobs = agent.scan()
        processed_files = list(processed_dir.glob("*.*"))
        processed_invoices = [f for f in processed_files if not f.name.endswith('.meta.json')]
        
        print(f"Summary:")
        print(f"   Files in watch directory: {len(final_jobs)}")
        print(f"   Files in processed directory: {len(processed_invoices)}")
        print(f"   Total processed (this session): {len(jobs) - len(final_jobs)}")
        
        if final_jobs:
            print(f"\nRemaining files in watch directory:")
            for job in final_jobs:
                print(f"   - {Path(job['file_path']).name}")
        
        if processed_invoices:
            print(f"\nRecent processed files:")
            for f in sorted(processed_invoices, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
                print(f"   - {f.name}")
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        print(f"\nTips:")
        print(f"   - Add files to: {watch_dir.absolute()}")
        print(f"   - View processed files in: {processed_dir.absolute()}")
        print(f"   - Run this script again to test with new files")
    
    try:
        asyncio.run(test_agent_with_real_directory())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during testing: {e}")
        import traceback
        traceback.print_exc()