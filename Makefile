build:
	@docker buildx build --push --platform linux/amd64 -t dr.meskatech.com/traefik2pihole:latest .

deploy_old: build
	@echo "Deploying ..."; \
	ssh root@swarm5 -C "docker service update --image dr.meskatech.com/traefik2pihole:latest  traefik2pihole_traefik2pihole --force"



remote = root@python-scripts

deploy:
	ssh $(remote) -C "cd /opt/timing2paprika && git pull";\	