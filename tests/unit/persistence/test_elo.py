from persistence.elo import compute_new_ratings


class TestComputeNewRatings:

    def test_equal_ratings_winner_gains_half_k_factor(self):
        new_a, new_b = compute_new_ratings(1200, 1200, result_a=1.0, k_factor=32)
        assert new_a == 1216
        assert new_b == 1184

    def test_draw_between_equal_ratings_is_unchanged(self):
        new_a, new_b = compute_new_ratings(1200, 1200, result_a=0.5, k_factor=32)
        assert new_a == 1200
        assert new_b == 1200

    def test_underdog_win_gains_more_than_expected_favorite_win(self):
        # Lower-rated A beats higher-rated B: A should gain more than the
        # equal-ratings case; B should lose more.
        underdog_gain, favorite_loss = compute_new_ratings(1100, 1300, result_a=1.0, k_factor=32)
        assert underdog_gain - 1100 > 16
        assert 1300 - favorite_loss > 16

    def test_total_points_are_conserved(self):
        # ELO is zero-sum for equal k_factor on both sides.
        new_a, new_b = compute_new_ratings(1187, 1263, result_a=0.0, k_factor=32)
        assert (new_a - 1187) == -(new_b - 1263)
