# make test                 — unit + end-to-end tests on local Spark (no Azure needed)
# make infra                — stage 1 (Azure) then stage 2 (Unity Catalog)
# make data                 — generate sample CSVs and upload them to the landing container
# make deploy run           — deploy the Databricks job and run bronze → silver → gold
# make destroy              — tear everything down
TF1 = terraform -chdir=infra/azure
TF2 = terraform -chdir=infra/databricks
out = $(shell $(TF1) output -raw $(1))

test:
	python -m pytest -q tests

infra:
	$(TF1) init && $(TF1) apply
	$(MAKE) uc   # separate make call so stage-1 outputs exist when stage 2 reads them

uc:
	$(TF2) init && $(TF2) apply \
	  -var workspace_url=$(call out,workspace_url) \
	  -var workspace_resource_id=$(call out,workspace_resource_id) \
	  -var access_connector_id=$(call out,access_connector_id) \
	  -var storage_account_name=$(call out,storage_account_name)

data:
	python sample_data/make_sample.py
	az storage blob upload-batch --auth-mode login --account-name $(call out,storage_account_name) \
	  --destination landing --destination-path synthea --source sample_data/synthea --overwrite

deploy:
	DATABRICKS_HOST=$(call out,workspace_url) databricks bundle deploy -t dev --var="landing=$(call out,landing_path)"

run:
	DATABRICKS_HOST=$(call out,workspace_url) databricks bundle run lakehouse_pipeline -t dev

destroy:
	-DATABRICKS_HOST=$(call out,workspace_url) databricks bundle destroy -t dev --auto-approve
	-$(TF2) destroy -auto-approve \
	  -var workspace_url=$(call out,workspace_url) -var workspace_resource_id=$(call out,workspace_resource_id) \
	  -var access_connector_id=$(call out,access_connector_id) -var storage_account_name=$(call out,storage_account_name)
	$(TF1) destroy

.PHONY: test infra uc data deploy run destroy
