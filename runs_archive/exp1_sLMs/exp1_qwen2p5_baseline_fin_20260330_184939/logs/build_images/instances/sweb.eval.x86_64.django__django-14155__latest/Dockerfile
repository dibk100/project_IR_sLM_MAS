FROM --platform=linux/x86_64 sweb.env.py.x86_64.517560d64be75e8a7d67c5:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
