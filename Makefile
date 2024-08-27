build:
	@docker buildx build --push --platform linux/amd64 -t dr.meskatech.com/traefik2pihole:latest .

deploy: build
	@echo "Deploying ..."; \
	ssh root@swarm5 -C "docker service update --image dr.meskatech.com/traefik2pihole:latest  traefik2pihole_traefik2pihole --force"