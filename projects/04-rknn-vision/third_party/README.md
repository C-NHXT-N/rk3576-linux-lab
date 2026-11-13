The native build uses the unmodified Rockchip RKNN Toolkit2 v2.5.0 C API header. From the vision project directory, run `python fetch_sdk.py --role header` to download the pinned file here. The header and SDK binaries are obtained separately from this repository.

Source: https://github.com/airockchip/rknn-toolkit2/blob/v2.5.0/rknpu2/runtime/Linux/librknn_api/include/rknn_api.h

SHA256: `2d4160cd868efd7b83a72587e411c16d6972da5876e067bd73665cea778ce666`

Its original copyright and terms remain in the header. The backend dynamically loads the existing project Runtime; this directory does not supply or replace a Runtime binary.
