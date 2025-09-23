class ImmutableKeyError(TypeError):
    """Accessed key is immutable so does not allow changes or removals."""

    def __init__(self, key, msg=None):
        self.immutable_key = key
        if not msg:
            msg = f"Key \"{key}\" is immutable and does not allow changes."
        super().__init__(msg)
