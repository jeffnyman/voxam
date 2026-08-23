from assertpy import assert_that

from voxam.infocom import TITLES, title


# The catalog names every release the header identifies: the
# treaty's own examples land on their titles, the one beta whose
# serial earns a checksum is keyed with it, and even Enchanter's
# 999999 test copy answers by name.
def test_the_catalog_names_the_releases() -> None:
    assert_that(title("ZCODE-12-860926")).is_equal_to("Trinity")
    assert_that(title("ZCODE-88-840726")).is_equal_to("Zork 1")
    assert_that(title("ZCODE-2-AS000C")).is_equal_to("Zork 1")
    assert_that(title("ZCODE-15-999999")).is_equal_to("Enchanter")
    assert_that(title("ZCODE-59-000001-D070")).is_equal_to(
        "Leather Goddesses of Phobos"
    )


# What the catalog cannot name, it does not: unknown identities,
# no identity at all, and the genuinely ambiguous release 5
# serial XXXXXX, which two different games shipped under.
def test_the_unknown_stay_unnamed() -> None:
    assert_that(title("ZCODE-347-890714")).is_none()
    assert_that(title("GLULX-1-000001-00000000")).is_none()
    assert_that(title(None)).is_none()
    assert_that("ZCODE-5-XXXXXX" in TITLES).is_false()
