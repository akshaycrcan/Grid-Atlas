"""Stable seven-part diligence template; missing fields are never filled with estimates."""

SECTIONS = {
    "Power": {
        "utility_capacity": "Total utility capacity (MW)",
        "contracted_power": "Contracted power (MW)",
        "expansion_power": "Power available for expansion (MW)",
        "interconnection": "Utility load-interconnection queue and timeline",
        "electricity_rates": "Rate structure and electricity price ($/kWh)",
        "energy_mix": "Energy mix, carbon intensity, renewables and PPAs",
        "rack_density": "Power density (kW/rack)",
    },
    "Cooling and water": {
        "cooling": "Cooling method",
        "pue": "PUE: measured versus design/marketing target",
        "water": "Water source, consumption and WUE",
        "water_risk": "Drought exposure and water permitting",
    },
    "Location and connectivity": {
        "latency": "Demand proximity and measured latency",
        "fiber": "Fiber routes and internet exchanges",
        "carriers": "On-site carriers and carrier neutrality",
        "hazards": "Flood, seismic and extreme-heat exposure",
        "regulatory": "Political and regulatory conditions",
    },
    "Design and reliability": {
        "tier": "Uptime tier or equivalent certification",
        "redundancy": "Redundancy and generator/UPS runtime",
        "outages": "Outage history and SLA terms",
        "security": "Physical security and compliance certifications",
    },
    "Economics": {
        "colo_price": "Colocation price ($/kW/month)",
        "contract_terms": "Contract length, escalators and power pass-through",
        "build_cost": "Build cost per MW",
        "vacancy": "Market vacancy and absorption",
    },
    "Market and competitive landscape": {
        "operators_tenants": "Operators, competitors and disclosed tenants",
        "preleasing": "Pre-leasing on planned supply",
        "pipeline": "Pipeline of new builds in the market",
    },
    "Land, permitting and community": {
        "zoning": "Zoning and environmental approvals",
        "incentives": "Tax incentives",
        "community": "Community opposition and local decisions",
        "land": "Land availability and documented substation proximity",
        "construction": "Labor and equipment lead times",
    },
}

MISSING = "Details not available."
METRIC_CATEGORY = {key: section for section, fields in SECTIONS.items() for key in fields}


def research_scope() -> str:
    return "\n".join(
        f"{section}: " + "; ".join(f"{key}={label}" for key, label in fields.items())
        for section, fields in SECTIONS.items()
    )
