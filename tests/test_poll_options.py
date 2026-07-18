import pytest

from app.core.exceptions import InvalidPollOptionsError
from app.services.poll_options import parse_poll_options, validate_poll_options


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Плов  Пицца  Бургеры", ["Плов", "Пицца", "Бургеры"]),
        ("Хачапури по-аджарски\nЛагман", ["Хачапури по-аджарски", "Лагман"]),
        ("  Рис с овощами   Том-ям  ", ["Рис с овощами", "Том-ям"]),
        ("🍜 Рамен\u2003\u2003🥟 Манты", ["🍜 Рамен", "🥟 Манты"]),
    ],
)
def test_parse_poll_options_supports_names_unicode_and_separators(raw, expected):
    assert parse_poll_options(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Только один",
        "1  2  3  4  5  6  7",
        "Плов  плов",
        "Straße  STRASSE",
        f"{'я' * 41}  Пицца",
        "<b>Плов</b>  Пицца",
        "Плов\tс мясом  Пицца",
    ],
)
def test_parse_poll_options_rejects_limits_duplicates_and_markup(raw):
    with pytest.raises(InvalidPollOptionsError):
        parse_poll_options(raw)


def test_validate_poll_options_accepts_boundary_lengths():
    assert validate_poll_options(["я", "🍕" * 40]) == ["я", "🍕" * 40]
