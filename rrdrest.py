import os

from fastapi import FastAPI, HTTPException
from backend.RRD_parse import RRD_parser
from typing import Optional

rrd_rest = FastAPI(
    title="RRDReST",
    description="Makes RRD files API-able",
    version="0.3",
)


@rrd_rest.get(
    "/",
    summary="Get the data from a RRD file, takes in a rrd file path"
    )
async def get_rrd(rrd_path: str, epoch_start_time: Optional[int] = None, epoch_end_time: Optional[int] = None, rrd_timezone: Optional[str] = None):
    """
    Fetches data from an RRD file.

    Args:
        rrd_path: Path to the RRD file.
        epoch_start_time: Start time in epoch seconds (optional).
        epoch_end_time: End time in epoch seconds (optional).
        rrd_timezone: Timezone of the RRD file (optional). If None, assumes UTC.

    Returns:
        JSON data from the RRD file.

    Raises:
        HTTPException: 
            - 404: If the RRD file is not found.
            - 500: If epoch_start_time or epoch_end_time is specified without the other, 
                   or if an error occurs during RRD parsing.
    """

    is_file = os.path.isfile(rrd_path)
    if is_file:
        if (epoch_start_time and not epoch_end_time) or (epoch_end_time and not epoch_start_time):
            raise HTTPException(status_code=500, detail="If epoch start or end time is specified both start and end time MUST be specified")
        #try:
        rr = RRD_parser(
                            rrd_file=rrd_path,
                            start_time=epoch_start_time,
                            end_time=epoch_end_time,
                            rrd_timezone=rrd_timezone 
                            )
        r = rr.compile_result()
        return r
        #except Exception as e:
        #    HTTPException(status_code=500, detail=f"{e}")
    raise HTTPException(status_code=404, detail="RRD not found")
