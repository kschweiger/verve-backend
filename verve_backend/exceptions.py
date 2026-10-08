class InvalidCombinationError(Exception):
    pass


class InvalidDataError(Exception):
    pass


class VerveImportError(Exception):
    pass


class StoredTrackFileUnavailableError(Exception):
    def __init__(self, *, bucket: str, key: str) -> None:
        self.bucket = bucket
        self.key = key
        super().__init__(
            f"Stored track file is not available in bucket '{bucket}' (key '{key}')"
        )
