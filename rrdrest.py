import os

from concurrent.futures import ThreadPoolExecutor
from backend.RRD_parse import RRD_parser
from fastapi import FastAPI, HTTPException
from typing import Optional

rrd_rest = FastAPI(
    title="RRDReST",
    description="Makes RRD files API-able",
    version="0.4",
)

# Sync/Async helper function
def process_file(file_path, start_time, end_time, epoch_output, timeshift, baseline):
    rr = RRD_parser(
        rrd_file=file_path,
        start_time=start_time,
        end_time=end_time,
        epoch_output=epoch_output,
        timeshift=timeshift,
        baseline=baseline,
    )
    return file_path, rr.compile_result()

@rrd_rest.get(
    "/",
    summary="Get the data from a RRD file, takes in a rrd file path",
    description="Fetches the RRD file data for the specified time range (if provided). "
                "If epoch times are not provided, the last 24 hour of data will be fetched.",
    )
async def get_rrd(
    rrd_path: Optional[str] = None,
    rrd_paths: Optional[List[str]] = None,
    epoch_start_time: Optional[int] = None,
    epoch_end_time: Optional[int] = None,
    epoch_output: Optional[bool] = False,
    timeshift: Optional[str] = None,
    baseline: Optional[str] = None,
):
    # Ensure at least one of rrd_path or rrd_paths is provided, but not both
    if (rrd_path is None and rrd_paths is None) or (rrd_path is not None and rrd_paths is not None):
        raise HTTPException(
            status_code=400,
            detail="Exactly one of 'rrd_path' or 'rrd_paths' must be provided"
        )

    # Determine single or multi file mode
    if rrd_path is not None:
        is_single_file = True
        files_to_process = [rrd_path]
    else:
        files_to_process = rrd_paths
        is_single_file = False

    # Check if all files exist
    missing_files = [path for path in files_to_process if not os.path.isfile(path)]
    if missing_files:
        raise HTTPException(status_code=404, detail=f"RRD files not found: {', '.join(missing_files)}")

    if (epoch_start_time and not epoch_end_time) or (epoch_end_time and not epoch_start_time):
        raise HTTPException(status_code=400, detail="If epoch start or end time is specified both start and end time MUST be specified")

    if (timeshift and baseline):
        raise HTTPException(status_code=400, detail="Cannot use both timeshift and baseline")

    try:
        if is_single_file:
            # Single file mode: process synchronously in thread and return directly
            loop = asyncio.get_running_loop()
            _, result = await loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                process_file,
                rrd_path,
                epoch_start_time,
                epoch_end_time,
                epoch_output,
                timeshift,
                baseline
            )
            return result
        else:
            # Multiple file mode: process concurrently and return dictionary
            loop = asyncio.get_running_loop()
            tasks = []
            with ThreadPoolExecutor() as executor:
                for file_path in files_to_process:
                    tasks.append(
                        loop.run_in_executor(
                            executor,
                            process_file,
                            file_path,
                            epoch_start_time,
                            epoch_end_time,
                            epoch_output,
                            timeshift,
                            baseline
                        )
                    )
                results_list = await asyncio.gather(*tasks)
            results = {file_key: result for file_key, result in results_list}
            return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing RRD file(s): {e}")
