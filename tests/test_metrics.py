"""Unit tests for runtime.metrics."""
from __future__ import annotations

import math

import pytest

from modelforge.runtime.metrics import classification, forecasting


class TestForecasting:
    def test_perfect_prediction(self):
        y = [1.0, 2.0, 3.0, 4.0]
        assert forecasting.mae(y, y) == 0.0
        assert forecasting.rmse(y, y) == 0.0
        assert forecasting.mape(y, y) == 0.0
        assert forecasting.smape(y, y) == 0.0

    def test_mae_basic(self):
        # |1-2| + |3-1| = 3, /2 = 1.5
        assert forecasting.mae([1, 3], [2, 1]) == 1.5

    def test_rmse_basic(self):
        # sqrt((1+4)/2) = sqrt(2.5)
        assert forecasting.rmse([1, 3], [2, 1]) == pytest.approx(math.sqrt(2.5))

    def test_mape_skips_zeros(self):
        # 第一对 y=0 跳过，剩 |10-12|/10 = 0.2
        assert forecasting.mape([0, 10], [5, 12]) == pytest.approx(0.2)

    def test_mape_all_zero_raises(self):
        with pytest.raises(ValueError):
            forecasting.mape([0, 0], [1, 2])

    def test_smape_range(self):
        v = forecasting.smape([1, 2, 3], [3, 2, 1])
        assert 0 <= v <= 2

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            forecasting.mae([1, 2], [1, 2, 3])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            forecasting.mae([], [])

    def test_compute_all_handles_failures(self):
        # 全零 → mape None，其它仍能算
        out = forecasting.compute_all([0, 0], [1, 2])
        assert out["mape"] is None
        assert out["mae"] == 1.5
        assert out["rmse"] == pytest.approx(math.sqrt(2.5))


class TestClassification:
    def test_perfect(self):
        y = ["a", "b", "a", "c"]
        assert classification.accuracy(y, y) == 1.0
        assert classification.precision_macro(y, y) == 1.0
        assert classification.recall_macro(y, y) == 1.0
        assert classification.f1_macro(y, y) == 1.0

    def test_accuracy_basic(self):
        # 3/4 对
        assert classification.accuracy(["a", "b", "a", "b"], ["a", "b", "a", "a"]) == 0.75

    def test_int_and_str_labels_mixed(self):
        # str("1") == str(1) → 同一类
        assert classification.accuracy([1, 2, 3], ["1", "2", "3"]) == 1.0

    def test_macro_f1_binary(self):
        # 2 真 a 都对，1 真 b 被预测为 a：a precision=2/3, recall=1; b precision=0, recall=0
        # f1_a = 2*(2/3)*1/(2/3+1) = (4/3)/(5/3) = 0.8
        # f1_b = 0
        # macro = 0.4
        f1 = classification.f1_macro(["a", "a", "b"], ["a", "a", "a"])
        assert f1 == pytest.approx(0.4)

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            classification.accuracy([1, 2], [1])

    def test_compute_all(self):
        out = classification.compute_all(["a", "b", "a"], ["a", "b", "a"])
        assert set(out) == {"accuracy", "precision_macro", "recall_macro", "f1_macro"}
        assert all(v == 1.0 for v in out.values())
