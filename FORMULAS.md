# Existing calculations and capacitor scenario formulas

Units: total three-phase kW/kVA/kvar, line-line voltage in kV, current in A,
conductor R/X in ohm/km, section length in km.

| Quantity | Formula / change |
|---|---|
| Apparent power | `S_kVA = sqrt(3)*V_kV*I_A`; this is kVA, not kW |
| Active power | `P_kW = S_kVA*PF` |
| Reactive demand | `Q_kvar = P_kW*tan(acos(PF))` |
| Initial bank sizing | `Qc = P*(tan(acos(PF_before))-tan(acos(PF_target)))`; this alone cannot select a location |
| Voltage-sensitive shunt bank | `Qc_actual = Qc_rated*(V_local/V_rated)^2` |
| Section current | `I = conjugate((P+jQ)*1000/(3*V_phase))`; sum downstream currents, then solve voltages iteratively |
| Section HT loss | `P_loss = 3*abs(I)^2*R*length/1000` |
| Voltage | `V_child = V_parent - (R+jX)*length*I` |
| Period energy | `E_loss = sum(P_loss_t*hours_t)`; compare identical periods before/after |
| Transformer peak loss | `core_kW + copper_rated_kW*loading_pu^2`, adding core loss, not multiplying it |
| Legacy loss factor | `LLF = 0.3*LF + 0.7*LF^2`; historical estimate, not a post-capacitor time-series model |
| Legacy annual loss corrected | `8760*(core_kW + LLF*(HT_peak_kW + copper_peak_kW))`, assuming energised throughout the year |

## Confirmed source issues

In `Load_Flow_Analysis CALCULATIONS.xlsx`, sheet `Load Flow Analysis`:

- `B3 = F3*F5*8760` uses load factor for energy loss. For the historical method
  use the loss factor from `B6`, and annualise transformer core loss separately.
- `B14 = (F18*F6^2)*F19` multiplies copper loss by core loss. Use
  `F18*F6^2+F19` if F18/F19 are the rated copper/core loss inputs in kW.
- `B4` hardcodes conductor ampacity 535 although `F8` is the capacity input.
- `F13` (wire factor) is blank while `B13` calculates it. `B5` therefore depends
  on a missing input unless it is manually filled. Prefer the dimensional
  voltage/current equations above instead of an unexplained wire factor.
- Several inputs are blank, and formula values are not cached. This workbook
  is a partial template, not an independently verified working result.

In `MANSOORABAD YEARLY LOSSES.xlsx`, each monthly sheet:

- `N` already adds core loss correctly: `copper*DF^2+core`.
- `AA15 = Z15*X15*8760` applies LLF to total peak loss, including core.
  Separate core before annualisation.
- Each month contains an annual-equivalent `*8760` result. Do not sum twelve
  annual-equivalent estimates to report a yearly total. Use actual monthly
  hours and monthly demand/loss profiles instead.
- `O` uses hardcoded 11 kV while other calculations reference the bus voltage
  input. Changing voltage must update all calculations consistently.

In the supplied formula image, transformer loss is also shown as a product of
copper and core losses. The monthly workbook uses the additive form instead.

## Location matters

A capacitor supplies reactive current along the path between its electrical
node and the source. Recalculate each section, rather than replacing PF for the
whole feeder. Other branches can also change slightly due to bus-voltage changes
in a physical load flow. Source Q must be reported with its sign to reveal a
leading condition.

## Source basis

User-uploaded Excel workbooks and `Formula sheet.png` in `Capacitor workflow.zip`;
the solver and engineering handoff in `capacitor skills.zip`; USAID Power
Distribution Program Planning Guide, printed pp. 38–40, section 4.4/4.4.1 and
Appendix G. Guide PDF p.47 discusses matching capacitors to reactive loads and
practical standard sizes. PDF p.48 describes the half-to-two-thirds feeder
location heuristic for simplified distributed loads; it is not an exact GIS
location algorithm. No external acceptance-standard compliance is claimed.
