FROM --platform=linux/x86_64 sweb.env.py.x86_64.01c6e6c71349434a25f883:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
