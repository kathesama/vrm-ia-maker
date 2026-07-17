from typing import Final

LK_NBLCK: Final[int]
LK_UNLCK: Final[int]

def locking(fd: int, mode: int, nbytes: int) -> None: ...
