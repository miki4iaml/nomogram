# Third-party data of the examples

## COARE 3.6 test data

`coare36_test.csv` holds one row in 20 of the test data of the COARE 3.6
bulk flux algorithm, `test_36_data.txt`, and of its outputs,
`test_36_output_withnowavesinput_withwarmlayer.txt`, from the repository
NOAA-PSL/COARE-algorithm (<https://github.com/NOAA-PSL/COARE-algorithm>),
directory `Python/COARE3.6`, commit
`bd1cac80d2dae454e699f9ef46204dfd88086a71`.

Columns: the inputs `jd` (day of the year), `u` (wind speed, m/s, at
`zu`, m), `ta` (air temperature, °C, at `zt`), `rh` (relative humidity,
%, at `zq`), `P` (pressure, hPa), `tsnk` (sea temperature, °C), `lat`
(latitude, degrees), `zi` (height of the boundary layer, m, 600 in the
test); the outputs `Qs` (specific humidity at the sea surface, g/kg),
`usr`, `tsr`, `qsr` (scales of wind, m/s, temperature, K, and specific
humidity, kg/kg), `L` (Obukhov length, m) and `zo` (roughness length,
m). Changes: the rows and columns were selected, the values rounded to
seven significant digits, and `T_skin` added, the skin temperature COARE
computes with its warm layer and cool skin, `tsnk + dT_warm_to_skin -
dT_skinx` (°C), as its code documents.

```text
MIT License

Copyright (c) 2022 NOAA/OAR/ESRL Physical Sciences Laboratory

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
