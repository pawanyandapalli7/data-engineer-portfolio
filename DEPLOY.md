# Deploying this repo, step by step

Five parts, in the order that gets you the most for the least effort:

1. Put the repo on GitHub (15 min)
2. Turn on the live test evidence (5 min)
3. Deploy the Azure lakehouse and keep the proof (about 1 hour, under $5 if you tear it down the same day)
4. Run the LLM evaluation for real (15 min, cents)
5. Run the local stacks for screenshots (optional)

Then update the website (`site-updates.md`, delivered with this repo).

---

## Part 0: Tools

| Tool | Why | macOS | Windows |
|---|---|---|---|
| Git | push the repo | `brew install git` | `winget install Git.Git` |
| Python 3.11 or 3.12 | run tests and scripts | `brew install python@3.12` | `winget install Python.Python.3.12` |
| Java 17 | local Spark tests | `brew install openjdk@17` | `winget install EclipseAdoptium.Temurin.17.JDK` |
| Azure CLI | log in to Azure | `brew install azure-cli` | `winget install Microsoft.AzureCLI` |
| Terraform ≥ 1.6 | create Azure resources | `brew install hashicorp/tap/terraform` | `winget install Hashicorp.Terraform` |
| Databricks CLI ≥ 0.218 | deploy and run the job | `brew install databricks/tap/databricks` | `winget install Databricks.DatabricksCLI` |
| make | run the Makefile | preinstalled | use **WSL** (Ubuntu) for Part 3 |
| Docker Desktop | Part 5 only | docker.com | docker.com |

Check: `git --version && python3 --version && java -version && az version && terraform version && databricks version`

---

## Part 1: Put the repo on GitHub

Replace the files in your existing repo but keep its history.

```bash
git clone https://github.com/pawanyandapalli7/data-engineer-portfolio.git
cd data-engineer-portfolio

# delete everything except .git, then copy the new files in
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
unzip ~/Downloads/data-engineer-portfolio.zip -d /tmp/newrepo
cp -R /tmp/newrepo/data-engineer-portfolio/. .

git add -A
git commit -m "Restructure portfolio: tested projects, CI, MLOps and dbt, live evidence"
git push origin main
```

Then on github.com, on the repo page, click the gear next to **About**:

- Description: `Data and ML platform projects: Azure Databricks lakehouse, MLOps with MLflow, dbt, CDC, feature store, RAG. Every project tested in CI.`
- Website: `https://www.pawanyandapalli.com`
- Topics: remove `hipaa-compliance` and `dbt` if present, then add `data-engineering`, `databricks`, `delta-lake`, `unity-catalog`, `mlops`, `mlflow`, `dbt`, `terraform`, `pyspark`, `snowflake`, `kafka`, `pgvector`.

Pin the repo on your profile: github.com/pawanyandapalli7 → **Customize your pins**.

---

## Part 2: Turn on the live test evidence

1. Repo → **Settings** → **Pages** → **Source: GitHub Actions**.
2. Repo → **Actions** → open the latest **CI** run. If it already finished before step 1, click **Re-run all jobs**.
3. When it's green, open
   `https://pawanyandapalli7.github.io/data-engineer-portfolio/`.
   You should see the evidence table. The README badges switch from "invalid" to "N passing" within a few minutes (shields.io caches).

If a job is red, open it, copy the last 50 lines of the log, and fix or ask for help. Common first-run causes:

| Job | Likely cause | Fix |
|---|---|---|
| `terraform · …` | a provider version changed | run `terraform init -upgrade && terraform validate` locally in that folder |
| `python · patterns-airflow` | pip resolver timeout | re-run the job |
| `evidence` | Pages not enabled yet | do step 1, then re-run |

---

## Part 3: Deploy the Azure lakehouse

### 3.1 Check the subscription (5 min)

You need a **Pay-As-You-Go** subscription (free trials have too little vCPU quota) where you are **Owner**, or Contributor + User Access Administrator.

```bash
az login
az account list -o table                       # find your subscription id
az account set --subscription <SUBSCRIPTION_ID>

# The job cluster uses 2 × Standard_D4ds_v5 = 8 vCPUs. Check quota:
az vm list-usage --location westus2 -o table | grep -i "DDSv5\|Total Regional"
```

You need at least 8 free vCPUs in both lines. If not, request an increase (Portal → **Quotas** → Compute → `Standard DDSv5 Family vCPUs` → 8), or pick another region in step 3.2.

### 3.2 Configure

```bash
cd projects/azure-lakehouse
cp infra/azure/example.tfvars infra/azure/terraform.tfvars
```

Edit `infra/azure/terraform.tfvars`:

```hcl
subscription_id    = "<SUBSCRIPTION_ID>"
alert_email        = "pawanyandapalli1@gmail.com"
location           = "westus2"
monthly_budget_usd = 25
```

`terraform.tfvars` is git-ignored. Don't commit it.

### 3.3 Create the infrastructure (~10 min)

```bash
make infra
```

Type `yes` twice: once for Azure (resource group, ADLS Gen2, Databricks workspace, access connector, budget alert) and once for Unity Catalog (storage credential, external locations, catalog, schemas).

If stage 2 fails with "metastore not assigned", open the workspace URL once (`terraform -chdir=infra/azure output -raw workspace_url`), wait two minutes, and run `make uc`.

### 3.4 Load data and run the pipeline (~10 min)

```bash
make data          # generates the sample CSVs and uploads them to the landing container
make deploy run    # deploys the job and runs bronze → silver → gold
```

If `make data` returns 403, the storage role for your user is still propagating. Wait five minutes and run it again.

`make run` prints a run URL. Open it: all three tasks should be green.

### 3.5 Look at the results

In the workspace: **SQL Editor** → choose a SQL warehouse (create a 2X-Small **serverless** one if none exists; it auto-stops).

```sql
SELECT * FROM lakehouse_demo.gold.claims_by_month ORDER BY month;
SELECT _failed_checks, count(*) FROM lakehouse_demo.silver.claims_quarantine GROUP BY 1;
SELECT count(*) FROM lakehouse_demo.gold.fact_claim_lines;
```

### 3.6 Show SCD Type 2 history with a second run (optional, 5 min)

```bash
python - <<'PY'
import csv
p = "sample_data/synthea/patients.csv"
rows = list(csv.DictReader(open(p, newline="")))
moved = next(r for r in rows if r["GENDER"] in ("M", "F"))
moved["ZIP"], moved["COUNTY"] = "89501", "Washoe"
w = csv.DictWriter(open(p, "w", newline=""), fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
print("moved", moved["Id"])
PY
az storage blob upload-batch --auth-mode login \
  --account-name $(terraform -chdir=infra/azure output -raw storage_account_name) \
  --destination landing --destination-path synthea --source sample_data/synthea --overwrite
make run
```

```sql
SELECT patient_id, zip, valid_from, valid_to, is_current
FROM lakehouse_demo.gold.dim_patient
WHERE patient_id IN (SELECT patient_id FROM lakehouse_demo.gold.dim_patient WHERE NOT is_current)
ORDER BY patient_id, valid_from;
```

### 3.7 Keep the proof

Create `projects/azure-lakehouse/docs/deployment/` and save:

| File | How |
|---|---|
| `job-run.png` | screenshot of the green run graph (bronze → silver → gold) |
| `claims_by_month.png` | screenshot of the query result |
| `quarantine.png` | screenshot of the quarantine query |
| `scd2-history.png` | screenshot from 3.6, if you did it |
| `job-run.json` | `databricks jobs get-run <RUN_ID> -o json > docs/deployment/job-run.json` (the run id is in the run URL). Delete your email address from it before committing |

Crop the browser address bar out of screenshots. Then:

1. In `projects/azure-lakehouse/README.md`, change the **Deployed** row to
   `Yes, on Azure Databricks (<month year>), then torn down. Evidence: [docs/deployment](docs/deployment)`
   and add the screenshots under a `## Deployment evidence` heading.
2. In `scripts/evidence.py`, set `deployed=True` for `azure-lakehouse`.
3. In the root `README.md`, change "None of these is deployed to a cloud account yet" to
   "The Azure lakehouse has been deployed and run on Azure Databricks ([evidence](projects/azure-lakehouse/docs/deployment)); the others run locally and in CI."

```bash
git add -A && git commit -m "Azure lakehouse: deployment evidence" && git push
```

### 3.8 Tear it down (same day)

```bash
make destroy
```

Type `yes`. Then check Portal → **Resource groups**: the `lkh-*` group and the Databricks managed resource group should be gone. The workspace's NAT gateway costs about $1/day while it exists, so don't skip this.

---

## Part 4: Run the LLM evaluation for real

```bash
cd projects/llm-eval-harness
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
python src/compare_models.py
```

It writes JSON reports to `reports/`. Commit them, and add the real numbers to the project README in a `## Results` section with the date and model names. Six cases is small, so say so next to the numbers. Only then put results back on the website card.

---

## Part 5: Run the local stacks (optional, for screenshots and demos)

**MLOps model** (no keys needed):

```bash
cd projects/mlops-claims-model
docker compose run --rm train
docker compose up -d serve
curl localhost:8080/health
curl -X POST localhost:8080/predict -H 'content-type: application/json' -d '{"claims":[{"claim_amount":1200,"out_of_network":true,"prior_auth":false,"days_to_submit":75,"diagnosis_group":"cardio","place_of_service":"inpatient","member_age":61,"prior_denials_12m":2}]}'
```

For the MLflow UI: `pip install -r requirements.txt`, run the three `train` commands from the project README, then `mlflow ui --backend-store-uri sqlite:///mlflow.db` and open localhost:5000. A screenshot of the registry showing the `champion` alias is great on the website card.

**Feature store** (no keys needed): see `projects/feature-store/README.md` → Run.

**RAG** (needs `OPENAI_API_KEY`): see `projects/rag-pipeline/README.md` → Run.

**dbt** (no keys needed): `cd projects/dbt-claims-marts && pip install -r requirements.txt && dbt build --profiles-dir . && dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .`. The lineage graph makes a good screenshot.

---

## Checklist

- [ ] Part 1: pushed; About, topics and pin set
- [ ] Part 2: Pages on, CI green, badges show counts
- [ ] Part 3: lakehouse deployed, proof committed, **torn down**
- [ ] Part 4: eval run and results committed
- [ ] Website: links fixed, copy corrected, MLOps and dbt cards added, CI widget live
