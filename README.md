# RRDReST

A simple micro service for converting your RRDtool files to JSON vis REST API.

![rrdReST](/rrdshot.PNG)

## Getting started
### Local
- Ensure you have ```rrdtool``` installed and you can access the rrd files from the server
- Git clone the project ``` git clone https://github.com/slashdoom/RRDReST && cd RRDReST ```
- Install the requirements ```pip3 install -r requirements.txt```
- Run the app with uvicorn ```uvicorn rrdrest:rrd_rest --host "0.0.0.0" --port 9000```
- Access the swagger documentation via ```http://127.0.0.1:9000/docs```
### Docker
- git clone the project ``` git clone https://github.com/slashdoom/RRDReST && cd RRDReST ``` or copy the compose.yml file
- Modify the volumes to point to your RRDtool files
- docker compose up rrdrest

## Examples
- last 24 hours ```curl 127.0.0.1:9000/?rrd_path=tests/port-id15.rrd```
- epoch date time filter ```curl 127.0.0.1:9000/?rrd_path=tests/port-id15.rrd&epoch_start_time=1622109000&epoch_end_time=1624787400```
- time output in epoch ```curl 127.0.0.1:9000/?rrd_path=tests/port-id15.rrd&epoch_start_time=1622109000&epoch_end_time=1624787400&epoch_output=true```
- 7 day timeshift ```curl 127.0.0.1:9000/?rrd_path=tests/port-id15.rrd&epoch_start_time=1622109000&epoch_end_time=1624787400&timeshift=7d```
- 3 week baseline ```curl 127.0.0.1:9000/?rrd_path=tests/port-id15.rrd&epoch_start_time=1622109000&epoch_end_time=1624787400&baseline=3w```

## RRDtool
- tested with version 1.9

## Hat tips
* Forked from: https://github.com/tbotnz/RRDReST
* RRDtool: https://oss.oetiker.ch/rrdtool/
