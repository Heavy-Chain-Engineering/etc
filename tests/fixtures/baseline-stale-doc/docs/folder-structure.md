# Folder Structure (convention doc)

Data-access code for every domain lives at `src/<domain>/data_access.py`.
Runtime logic imports it from there and never queries the store directly.
