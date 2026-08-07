from assertpy import assert_that


def test_tautology() -> None:
    # value equality
    assert_that(1).is_equal_to(1)

    # type checking
    assert_that("testing").is_instance_of(str)

    # membership checking
    assert_that("testing").is_in("testing", "quality")

    # identity checking
    assert_that(None).is_same_as(None)
