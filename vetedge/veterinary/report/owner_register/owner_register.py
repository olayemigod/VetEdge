from vetedge.services.reporting_logic_v3 import execute_structured_report


def execute(filters=None):
    return execute_structured_report("Owner Register", filters)
