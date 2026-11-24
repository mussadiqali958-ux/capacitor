# Capacitor placement and HT line-loss study

This first version reads the existing Mansoorabad Excel layout, reconstructs its
electrical tree, screens capacitor locations and sizes, and exports before/after
results. It reuses the balanced radial solver supplied inside `capacitor skills.zip`.
The two original ZIP uploads remain unchanged.

## Run locally

Install Python 3.11+ and then, from this folder:

```powershell
py -m pip install -r requirements.txt
py study.py --workbook "MANSOORABAD YEARLY LOSSES.xlsx" --sheet JULY --profiles sample_data/profiles.csv --profile-basis assumed --output local-results
py -m unittest discover -s tests -v
```

The example profile is **assumed demonstration data**. Replace it with measured
annual duration bins or interval readings, with `period,hours,load_fraction` and
8760 total hours. `load_fraction` scales coincident nodal kW and kvar together.
It is relative to the selected workbook sheet's source-current input. Choosing
`measured` describes the profile only; it does not certify the node allocation.

Optional inputs:

```powershell
py study.py --workbook "MANSOORABAD YEARLY LOSSES.xlsx" --profiles my-profile.csv --profile-basis measured --gis HTLines.geojson --sizes 150,300,450,600,900 --kind switched --sites eligible-nodes.csv --output local-results
```

`eligible-nodes.csv` contains `node_id`. This restricts the electrical screen to
the nominated sites. It is not a pole-coordinate or field-access approval.
For shapefiles export HT lines to EPSG:4326 GeoJSON with GDAL or QGIS, preserving
`SectionID`, `LengthKM`, `ConductorN`:

```sh
ogr2ogr -f GeoJSON HTLines.geojson Mansoorabad_HTLines.shp -t_srs EPSG:4326
```

## Outputs

- `study_summary.json`: assumptions, source checksums, legacy vs physical baseline,
  core-loss correction, preliminary electrical bank, and annual HT loss changes.
- `candidate_ranking.csv`: all single-node/size cases, including rejection reasons.
- `period_comparison.csv`: before/after losses, source PF/kvar/current, voltage,
  loading and energy for each period.
- `section_comparison.csv`: every SectionID and period, before/after current,
  voltage, kW, and saved kWh.
- `gis_reconciliation.csv`: missing, duplicate, length and conductor conflicts.
- `nodes.csv`, `sections.csv`, `profiles.csv`: reproducible input to the original
  Studio application. These nodal demands are derived assumptions.

## What the ranking means

The single-bank search tests every permitted node and size. It rejects cases
with voltage outside 0.95–1.05 pu, loading over 100%, leading source PF in any
profile period, or no annual HT energy saving. These default screening limits
are not a utility-specific engineering acceptance standard. Switched banks use
a simple 0.6 load-fraction ON threshold, not a field controller.

Load allocation uses installed node kVA proportions and workbook source amps/PF.
It does not use measured transformer P/Q. Line losses make the calculated source
current differ from the workbook input; this is reported as **not calibrated**.
Conductor R/X are taken from the study without temperature correction.

GIS attribute checks do not prove geometry connectivity, as-operated switch
states, endpoint orientation or node-to-pole mapping. All geographic locations
remain explicitly unverified. The tool does not infer or export an installation
coordinate from a mismatched SectionID.

Savings cover HT conductor losses only. Transformer core/copper, LT, service,
bank dielectric losses and nontechnical/billing losses are not counted as
capacitor savings. A final design needs reconciled topology, metered P/Q across
light and peak loads, calibration, eligible pole locations and electrical review
of protection, harmonics and switching.

## Formula changes

See [FORMULAS.md](FORMULAS.md). The source workbooks are read-only and never
overwritten. Outputs are local; do not commit utility data to a public repository.
