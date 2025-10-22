FROM public.ecr.aws/docker/library/alpine:3.20
RUN apk add --no-cache curl
CMD sh -c 'end=$((SECONDS+180)); while [ $SECONDS -lt $end ]; do for i in $(seq 1 200); do curl -s https://api.fedocx.online/health > /dev/null; done; done; sleep 2'
