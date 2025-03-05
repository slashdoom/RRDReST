import asyncio
import os
import subprocess

from concurrent.futures import ThreadPoolExecutor
from backend.RRD_parse import RRD_parser
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional

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


# Health check endpoint
@rrd_rest.get(
    "/health",
    summary="Health check",
    description="Returns the status of the API and checks if rrdtool is available",
    response_model=dict
)
async def health_check():
    try:
        # Check rrdtool availability
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: subprocess.check_output("rrdtool --version", shell=True).decode('utf-8')
        )
        if "RRDtool 1." not in result:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unhealthy",
                    "version": rrd_rest.version,
                    "rrdtool": "not available"
                }
            )
        return {
            "status": "healthy",
            "version": rrd_rest.version,
            "rrdtool": "available"
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "version": rrd_rest.version,
                "rrdtool": f"error: {str(e)}"
            }
        )

# RRD Data endpoint
@rrd_rest.get(
    "/",
    summary="Get the data from a RRD file, takes in a rrd file path",
    description="Fetches the RRD file data for the specified time range (if provided). "
                "If epoch times are not provided, the last 24 hour of data will be fetched.",
    )
async def get_rrd(
    rrd_path: Optional[str] = None,
    rrd_paths: Optional[List[str]] = Query(None),
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
        # Handle both repeated params and comma-separated string, with optional aliases
        if rrd_paths and len(rrd_paths) == 1 and "," in rrd_paths[0]:
            # Comma-separated format: path1,path2:alias1,alias2
            entry = rrd_paths[0].strip()
            if ":" in entry:
                paths_part, aliases_part = entry.split(":", 1)
                paths = [p.strip() for p in paths_part.split(",")]
                alias_list = [a.strip() for a in aliases_part.split(",")]
                if len(paths) != len(alias_list):
                    raise HTTPException(
                        status_code=400,
                        detail="Number of paths and aliases must match in 'rrd_paths'"
                    )
                files_to_process = paths
                aliases = dict(zip(paths, alias_list))
            else:
                # No aliases provided, just paths
                files_to_process = [p.strip() for p in entry.split(",")]
                aliases = {p: p for p in files_to_process}
        else:
            # Repeated param format: rrd_paths=path1:alias1&rrd_paths=path2:alias2
            for entry in rrd_paths:
                if ":" in entry:
                    path, alias = entry.split(":", 1)
                    files_to_process.append(path.strip())
                    aliases[path.strip()] = alias.strip()
                else:
                    path = entry.strip()
                    files_to_process.append(path)
                    aliases[path] = path
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
            # Use aliases as keys if provided, otherwise use file paths
            results = {aliases[file_key]: result for file_key, result in results_list}
            return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing RRD file(s): {e}")
