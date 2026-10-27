"""Writes small Synthea-shaped CSVs (patients, claims, claims_transactions) so the
pipeline can run end to end without downloading anything. ~2% of rows are
deliberately bad so the Silver quarantine has something to catch.
For realistic volume, use the Synthea sample download in the README instead."""
import csv
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
out = Path(__file__).parent / "synthea"
out.mkdir(exist_ok=True)
uid = lambda: str(uuid.UUID(int=random.getrandbits(128)))
counties = [("CA", "Alameda", "94568"), ("CA", "Contra Costa", "94520"), ("NV", "Washoe", "89501"), ("CA", "Santa Clara", "95014")]

patients = []
with open(out / "patients.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Id", "BIRTHDATE", "DEATHDATE", "SSN", "FIRST", "LAST", "GENDER", "STATE", "COUNTY", "ZIP"])
    for i in range(300):
        pid = uid(); st, co, z = random.choice(counties)
        born = date(1940, 1, 1) + timedelta(days=random.randint(0, 29000))
        gender = random.choice("MF") if i % 50 else "U"                       # bad row: unknown gender
        w.writerow([pid, born.isoformat(), "", f"999-00-{i:04d}", f"First{i}", f"Last{i}", gender, st, co, z])
        patients.append(pid)

claims = []
with open(out / "claims.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Id", "PATIENTID", "PROVIDERID", "PRIMARYPATIENTINSURANCEID", "SERVICEDATE", "STATUS1", "OUTSTANDING1", "DIAGNOSIS1"])
    for i in range(1200):
        cid = uid(); served = date(2025, 1, 1) + timedelta(days=random.randint(0, 600))
        outstanding = f"{random.choice([0, 0, 0, 25, 60]):.2f}" if i % 60 else "-10.00"   # bad row: negative
        pid = random.choice(patients)
        w.writerow([cid, pid, uid(), uid(), f"{served.isoformat()}T09:30:00Z", "CLOSED", outstanding,
                    random.choice(["J45", "E11", "I10", "M54.5", "Z00.00"])])
        claims.append((cid, pid, served))

with open(out / "claims_transactions.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ID", "CLAIMID", "PATIENTID", "TYPE", "AMOUNT", "FROMDATE", "PROCEDURECODE"])
    for cid, pid, served in claims:
        charge = round(random.uniform(40, 400), 2)
        for typ, amt in (("CHARGE", charge), ("PAYMENT", round(charge * random.uniform(.6, 1), 2))):
            w.writerow([uid(), cid, pid, typ, f"{amt:.2f}", f"{served.isoformat()}T09:30:00Z", random.choice(["99213", "83036", "80053"])])
print("wrote", *[p.name for p in out.iterdir()])
