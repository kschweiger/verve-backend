from typing import Generic, Never, TypeIs, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


class Ok(Generic[T]):
    __match_args__ = ("value",)

    def __init__(self, value: T) -> None:
        self.value = value

    def unwrap(self) -> T:
        return self.value


class Err(Generic[E]):
    __match_args__ = ("error",)

    def __init__(self, error: E) -> None:
        self.error = error

    def unwrap(self) -> Never:
        raise ValueError(f"Called unwrap on Err: {self.error}")


Result = Union[Ok[T], Err[E]]


def is_ok(result: Result[T, E]) -> TypeIs[Ok[T]]:
    return isinstance(result, Ok)


if __name__ == "__main__":

    def func_a(a, b) -> Result[int, str]:
        if b == 0:
            return Err("Division by zero")
        return Ok(a // b)

    for result in [Ok(42), Err("An error occurred")]:
        match result:
            case Ok(value):
                print(f"Success with value: {value}")
            case Err(error):
                print(f"Error: {error}")

    res = func_a(10, 2)
    if is_ok(res):
        res
        print(res.value)
    else:
        print(f"Error from if/else: {res.error}")
