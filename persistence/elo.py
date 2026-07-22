K_FACTOR = 32


def _expected_score(rating: int, opponent_rating: int) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent_rating - rating) / 400))


def compute_new_ratings(rating_a: int, rating_b: int, result_a: float,
                         k_factor: int = K_FACTOR) -> tuple[int, int]:
    """Standard ELO update for a single game between A and B.

    `result_a` is A's actual score: 1.0 for a win, 0.0 for a loss, 0.5 for a
    draw. B's result is always the complement (1 - result_a) - there's no
    separate parameter for it, since a game only ever has one outcome.
    Returns (new_rating_a, new_rating_b), each rounded to the nearest int.
    """
    expected_a = _expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    result_b = 1.0 - result_a
    new_a = rating_a + k_factor * (result_a - expected_a)
    new_b = rating_b + k_factor * (result_b - expected_b)
    return round(new_a), round(new_b)
