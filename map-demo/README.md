# Mansoorabad capacitor impact map

Open **Mansoorabad_Capacitor_Map.html** in a browser. This single file works without installation and without internet, except for the optional street basemap. On Android, download the file and open it in Chrome or use the hosted demo. The before/after maps stack on narrow screens.

## Use the demo

1. Start with Stress demo (assumed 350 A / 0.80 PF), July input (260 A / 0.90 PF from the earlier workbook), or light-load demo (assumed 100 A / 0.90 PF).
2. Change the bank size; switch the bank ON/OFF.
3. Tap a mapped node and choose **Place capacitor at this node**, or choose a node in the dropdown.
4. Compare voltage in kV and pu, conductor current/loading, and HT line losses. Select voltage, loading, or voltage change colours.
5. Use **Find lowest-loss location** to compare the entered bank size at all surveyed electrical nodes. Read any remaining violations.
6. Zoom/pan, inspect the selected source-to-node voltage profile, and export the section results as CSV.

The default is 1,500 kVAr at electrical node 180075. This reproduces the preceding spreadsheet scenario. It is a demonstration rather than an installation recommendation.

## Sources and GIS reconciliation

- `Feeder_18.kmz.zip`: 69 survey line features, Mansoorabad / 043118, original WGS84 coordinates.
- `HTForm (3).csv`: current pole survey reference, source at 132 kV Old Thermal Plant. Pole numbers support the survey association; no projection assumption is made for CSV Easting/Northing.
- `Mansoorabad_Capacitor_Simple.xlsx`, Source data / July: 69 radial electrical branches, 70 nodes, 8,025 kVA transformer nameplate allocation; lengths, conductor ratings and R/X values.

Some section IDs, conductor names and lengths disagree between the map and the electrical workbook. Joining by those section IDs would colour the wrong mapped spans. This demo joins known electrical pole endpoints along the shortest connected survey geometry path instead. 65 electrical branches are routed on the survey network. Nodes 180001, 180002, 180003 are absent from the current map: their locations are interpolated along the source–180008 surveyed corridor using cumulative electrical length. Their four adjoining branches are dashed approximate connections. No claim is made that these synthetic electrical IDs are actual surveyed pole IDs.

`mapping-audit.csv` records every electrical branch and its geometry basis. Model impedances and distances retain electrical-workbook values. Survey-path routing is geographic matching, not proof of as-built electrical connectivity. Confirm joins and current equipment status before engineering use. Existing mapped capacitor equipment is not independently added to this baseline; the trial bank is incremental relative to the workbook baseline.

## Calculation method

Balanced, nominal-voltage three-phase linear radial estimate (not OpenDSS or SynerGEE):

- Head P = sqrt(3) × 11 kV × before A × PF (kW).
- Head Q = sqrt(3) × 11 kV × before A × sqrt(1 − PF²) (kVAr).
- Branch P and Q use downstream/nameplate-total kVA shares. Local kVA allocations conserve at every node.
- Subtract the bank's entered kVAr only on branches between its node and the source.
- I = sqrt(P² + Q²) / (sqrt(3) × 11) (A).
- Branch loss = 3 × I² × R(ohm/km) × length(km) / 1000 (kW).
- Vchild(pu) = Vparent(pu) − (P × R + Q × X) × length / (1000 × 11²).
- Source current and PF exclude line loss feedback. Active demand remains fixed.

Voltage changes propagate through shared upstream impedance to other branches, while the reactive-current change is confined to the source–capacitor path. Real banks have output proportional to voltage squared; this demo assumes constant kVAr. Transformer, LT, bank and service losses are excluded, as are phase imbalance, taps/regulators, harmonics, transients and losses in the flow iteration. 0.95–1.05 pu is a demo screening band, not a confirmed local utility requirement.

The location search compares one entered size at each non-source, non-interpolated model node. Passing nodes have zero thermal overloads, all node voltages in the demo band, non-leading source Q, and loss no higher than baseline. The lowest-loss passing node is selected. If none pass, it returns the lowest-loss trial and explicitly reports that no candidate passed every screen. It does not optimize bank sizes or perform a minimum-load/time-series installation study.

Background on capacitor control and measured-model calibration: https://opendss.epri.com/OpenDSSandStateEstimation.html . This implementation does not claim the accuracy of an OpenDSS model.

## Developer integration

- `dist/index.html`, `style.css`, `app.js`: dependency-free frontend. Serve the `dist` folder with any static host, including Cloudflare Pages.
- `dist/data.js`: embedded geographic/electrical network.
- `dist/engine.js`: standalone calculation engine; `solveNetwork(network, config, bankNode, bankKvar)`. CommonJS export is provided for Node integration.
- `network.json`: same network as plain JSON, including node coordinates, branch impedances, ratings and mapping status.
- `test-engine.cjs`: execute `node test-engine.cjs` (Node standard library only).
- `mapping-audit.csv`: join audit.
- `Mansoorabad_Capacitor_Map.html`: portable bundle generated from dist; rebuild it whenever dist changes.

For API integration, validate network topology and inputs, call the engine separately for bank OFF and ON, and return node voltages plus branch current/loading/losses. For production-grade results, replace the solver with a validated power-flow backend while keeping the UI data shape. Import future feeder files through a validated mapping stage; this demo intentionally ships a fixed inspected network, not a general-purpose importer.

## Verification

Automated checks: 69 connected acyclic branches, 70 finite node voltages, node kVA conservation, exact OFF/baseline equality, reproduction of the spreadsheet baseline, all-node capacitor trials, expected current and voltage behavior on/off upstream paths, and leading-Q detection at light load. UI checks: bank OFF/ON, location search, loading colours, preset change and reset.

Default assumed stress example:

| Metric | Before | After: 1500 kVAr, node 180075 |
|---|---:|---:|
| Lowest voltage | 10.605804 kV | 10.701127 kV |
| HT conductor loss | 110.078471 kW | 81.563819 kW |
| Source current | 350.000 A | 309.244 A |
| Source PF | 0.800000 | 0.905434 |
| Overloaded branches | 4 | 0 |

These are calculated scenario results, not measured feeder performance.
