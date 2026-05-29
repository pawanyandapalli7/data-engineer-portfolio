# GitHub Updates — Step-by-Step Guide

## 1. Update the Repo README
Replace `data-engineer-portfolio/README.md` with the contents of `README.md` in this folder.
Commit message: `docs: add Databricks/dbt certs, update skills, add portfolio badge`

---

## 2. Update the Repo Description & Topics
Go to: https://github.com/pawanyandapalli7/data-engineer-portfolio
Click the ⚙️ gear icon next to "About" (top right of the file list)

**Description — paste this exactly:**
```
Data & AI engineering portfolio — RAG pipelines, LLM evaluation, real-time feature stores, CDC pipelines · Python · Spark · Kafka · OpenAI · Databricks · Snowflake
```

**Website:**
```
https://pawan-portfolio-lime.vercel.app/
```

**Topics — add all of these:**
```
data-engineering
llm
rag
kafka
spark
snowflake
fastapi
pyspark
machine-learning
aws
databricks
dbt
redis
airflow
python
```

---

## 3. Create Your GitHub Profile README
This is the page people see at github.com/pawanyandapalli7

**Steps:**
1. Go to https://github.com/new
2. Set repository name to exactly: `pawanyandapalli7`
   (must match your username exactly — GitHub will show a special banner)
3. Check ✅ "Public"
4. Check ✅ "Add a README file"
5. Click "Create repository"
6. Edit the README.md and paste the contents of `PROFILE_README.md` in this folder
7. Commit: `docs: add GitHub profile README`

---

## 4. Pin the Portfolio Repo on Your Profile
1. Go to https://github.com/pawanyandapalli7
2. Click "Customize your profile"
3. Under "Pinned repositories", click "+" 
4. Add `data-engineer-portfolio`
5. Also pin any other repos you have (health-tracker, etc.)

---

## 5. Move aws_to_azure_mapping.md
Move it out of the repo root into `04_cloud_aws/`:
```bash
git mv aws_to_azure_mapping.md 04_cloud_aws/aws_to_azure_mapping.md
git commit -m "refactor: move azure mapping doc into cloud section"
git push
```

---

## 6. Add Meaningful Commit Messages Going Forward
The file table on GitHub shows blank commit messages — this makes the repo look
unmaintained. For every future commit use the format:
```
feat(module): what you added
fix(module): what you fixed  
docs(module): what you documented
refactor(module): what you restructured
```

Examples:
- `feat(11_rag_pipeline): add multi-tenant metadata filtering`
- `docs(readme): add Databricks Platform Architect certification`
- `fix(cdc_pipeline): handle late-arriving delete events`
