FROM python:3.10-alpine
RUN apk add --no-cache git rrdtool
RUN pip3 install --upgrade pip
RUN git clone https://github.com/slashdoom/RRDReST.git /opt
RUN pip3 install -r /opt/RRDReST/requirements.txt

WORKDIR /opt/RRDReST

ENTRYPOINT ["uvicorn", "rrdrest:rrd_rest"]
CMD ["--host", "0.0.0.0", "--port", "9000"]
