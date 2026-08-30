from app.datasources.demo import run_demo_source
from app.datasources.razorpay.source import run_razorpay_source

# Same dispatch-table idiom as investigation/router.py's CATEGORY_RUNNERS:
# add a source by adding one entry here, never an `if source == ...` chain.
SOURCES = {
    "demo": run_demo_source,
    "razorpay_test": run_razorpay_source,
}
