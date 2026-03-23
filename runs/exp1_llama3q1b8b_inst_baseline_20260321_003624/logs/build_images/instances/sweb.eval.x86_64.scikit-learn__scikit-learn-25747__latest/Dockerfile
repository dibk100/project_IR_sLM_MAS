FROM --platform=linux/x86_64 sweb.env.py.x86_64.e9ee528720708746d6ee8f:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
