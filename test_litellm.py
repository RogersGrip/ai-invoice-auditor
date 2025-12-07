try:
    import litellm
    print(f"Litellm Dir: {litellm.__file__}")
    from litellm import completion
    print("Litellm Import Success")
except Exception as e:
    import traceback
    traceback.print_exc()
