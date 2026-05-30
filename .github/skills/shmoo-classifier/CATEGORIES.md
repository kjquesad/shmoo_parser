# Shmoo Classification Categories

The shmoo classifier analyzes the spatial distribution of pass/fail cells in a 2D shmoo grid and assigns one of the following categories.

---

## red

**Description**: The shmoo is failing across nearly all points. The unit is essentially dead at this test — no passing region exists.

**Rule**: Total fail ratio ≥ 95%

**Typical cause**: Hard defect, catastrophic failure, or test setup issue.

```
XXXXXXX
XXXXXXX
XXXXXXX
XXXXXXX
XXXXXXX
```

---

## clean

**Description**: The shmoo passes across nearly all points. The unit has a wide operating margin.

**Rule**: Total fail ratio ≤ 2%

**Typical cause**: Healthy unit with good margins.

```
*******
*******
*******
*******
*******
```

---

## ceiling

**Description**: Failures are concentrated at high Y values (top of the shmoo). The unit fails at high voltage but passes at lower voltages.

**Rule**: Top-half fail ratio ≥ 75% AND bottom-half fail ratio ≤ 35%

**Typical cause**: Overvoltage sensitivity, oxide breakdown risk, or power delivery issue at high voltage.

```
XXXXXXX   ← high voltage (fails)
XXXXXXX
XXX****
*******
*******   ← low voltage (passes)
```

---

## floor

**Description**: Failures are concentrated at low Y values (bottom of the shmoo). The unit fails at low voltage but passes at higher voltages.

**Rule**: Bottom-half fail ratio ≥ 75% AND top-half fail ratio ≤ 35%

**Typical cause**: Vmin issue — the unit needs more voltage to operate correctly. Weak transistors or hold-time violations.

```
*******   ← high voltage (passes)
*******
****XXX
XXXXXXX
XXXXXXX   ← low voltage (fails)
```

---

## speed_limit

**Description**: Failures are concentrated at high X values (right side of the shmoo). The unit fails at high timing/frequency but passes at lower speeds.

**Rule**: Right-half fail ratio ≥ 70% AND left-half fail ratio ≤ 35%

**Typical cause**: Fmax limitation — the unit cannot operate at high frequencies. Setup-time violations.

```
         low X → high X
***XXXX
***XXXX
***XXXX
***XXXX
***XXXX
```

---

## slow_limit

**Description**: Failures are concentrated at low X values (left side of the shmoo). The unit fails at low timing/slow conditions but passes at higher speeds.

**Rule**: Left-half fail ratio ≥ 70% AND right-half fail ratio ≤ 35%

**Typical cause**: Hold-time violations at slow clock edges, or minimum pulse-width issues.

```
         low X → high X
XXXX***
XXXX***
XXXX***
XXXX***
XXXX***
```

---

## diagonal

**Description**: The pass/fail boundary follows a roughly diagonal line across the shmoo. This is the classic voltage-vs-timing tradeoff shape.

**Rule**: The boundary between pass and fail regions is monotonically increasing/decreasing with ≥65% consistency, spanning ≥30% of the X-axis.

**Typical cause**: Normal silicon behavior — higher voltage enables faster operation. The diagonal represents the V/F operating curve.

```
XXXX***   ← high voltage
XXX****
XX*****
X******
XXXX***   ← low voltage
  ↑ slow    fast ↑
```

---

## corner_top_left

**Description**: Failures concentrated in the top-left quadrant (high voltage, low timing).

**Rule**: Top-left quadrant fail ratio ≥ 70% AND average of other quadrants ≤ 30%

**Typical cause**: Combined high-voltage + slow-timing stress reveals a localized defect.

```
XXXX***
XXXX***
XXX****
*******
*******
```

---

## corner_top_right

**Description**: Failures concentrated in the top-right quadrant (high voltage, high timing).

**Rule**: Top-right quadrant fail ratio ≥ 70% AND average of other quadrants ≤ 30%

**Typical cause**: The unit breaks down under combined high-voltage + high-frequency stress.

```
***XXXX
***XXXX
****XXX
*******
*******
```

---

## corner_bottom_left

**Description**: Failures concentrated in the bottom-left quadrant (low voltage, low timing).

**Rule**: Bottom-left quadrant fail ratio ≥ 70% AND average of other quadrants ≤ 30%

**Typical cause**: Weak drive strength at low voltage combined with hold-time issues at slow clock.

```
*******
*******
XXX****
XXXX***
XXXX***
```

---

## corner_bottom_right

**Description**: Failures concentrated in the bottom-right quadrant (low voltage, high timing).

**Rule**: Bottom-right quadrant fail ratio ≥ 70% AND average of other quadrants ≤ 30%

**Typical cause**: Classic Vmin-at-Fmax — the unit cannot sustain high frequency at low voltage.

```
*******
*******
****XXX
***XXXX
***XXXX
```

---

## crack

**Description**: Failures are concentrated in the center of the shmoo, while the edges pass. The failing region looks like a crack or island in the middle.

**Rule**: Center fail ratio ≥ 55% AND edge fail ratio ≤ 35%

**Typical cause**: Intermittent defect that manifests only under specific V/T conditions in the middle of the operating range. Can indicate a narrow failing window.

```
*******
**XXX**
**XXX**
**XXX**
*******
```

---

## island

**Description**: The center passes but the edges fail — the inverse of a crack. A small passing "island" surrounded by failures.

**Rule**: Edge fail ratio ≥ 55% AND center fail ratio ≤ 35%

**Typical cause**: Very limited operating window — the unit only works in a narrow V/T range.

```
XXXXXXX
XX***XX
XX***XX
XX***XX
XXXXXXX
```

---

## mixed

**Description**: The failure pattern doesn't match any of the above categories. The spatial distribution is ambiguous or combines multiple patterns.

**Rule**: No other rule matches.

**Typical cause**: Multiple overlapping defects, noisy test conditions, or a novel failure mode not yet categorized.

---

## Summary Table

| Category | Fail Location | Confidence Metric |
|----------|--------------|-------------------|
| red | Everywhere (≥95%) | fail ratio |
| clean | Nowhere (≤2%) | 1 - fail ratio |
| ceiling | Top rows (high V) | top - bottom ratio |
| floor | Bottom rows (low V) | bottom - top ratio |
| speed_limit | Right cols (high timing) | right - left ratio |
| slow_limit | Left cols (low timing) | left - right ratio |
| diagonal | Monotonic boundary | boundary monotonicity |
| corner_* | Single quadrant | max quadrant - avg others |
| crack | Center region | center - edge ratio |
| island | Edge region | edge - center ratio |
| mixed | No clear pattern | 0.5 (default) |

---

## Tuning Thresholds

All thresholds are defined in `shmoo_classifier.py` → `classify_shmoo()`. To adjust sensitivity:

- **Lower a threshold** → more shmoos get classified into that category (more permissive)
- **Raise a threshold** → fewer shmoos match, more fall into "mixed" (more strict)

Priority order matters — the first matching rule wins. Current priority:
1. red → 2. clean → 3. diagonal → 4. ceiling → 5. floor → 6. speed_limit → 7. slow_limit → 8. corner → 9. crack → 10. island → 11. mixed
