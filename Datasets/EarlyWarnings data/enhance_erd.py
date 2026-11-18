import os
import pandas as pd

# Read cleaned data for samples
data_dir = r"C:\Users\abdel\OneDrive\Desktop\ACUD\Moamen\Oasis_READY_CLEAN_DATA_v4\Oasis_READY_CLEAN_DATA_v4\Code\data set\after process"
tables = {}
for f in os.listdir(data_dir):
    if f.endswith('_clean.csv') and not f.startswith('dim_'):
        name = f.replace('_clean.csv', '')
        try:
            df = pd.read_csv(os.path.join(data_dir, f))
            tables[name] = df
        except Exception as e:
            pass

col_desc = {
    'station_id': 'Unique identifier for monitoring station (AQ-XX for air quality, WQ-XX for water quality)',
    'timestamp': 'Timestamp of measurement/reading (ISO 8601 format, may include timezone offset +02:00)',
    'pm25': 'Fine particulate matter with diameter < 2.5 micrometers (μg/m³)',
    'pm10': 'Particulate matter with diameter < 10 micrometers (μg/m³)',
    'no2': 'Nitrogen dioxide concentration (μg/m³ or ppb)',
    'o3': 'Ground-level ozone concentration (μg/m³ or ppb)',
    'temp_c': 'Ambient/air temperature in degrees Celsius (°C)',
    'humidity_pct': 'Relative humidity as percentage (0-100%)',
    'bin_id': 'Unique identifier for smart waste bin (BIN-XXX format)',
    'fill_pct': 'Current fill level of bin as percentage of capacity (0-100%)',
    'building_id': 'Unique identifier for building in the district (B-XXXX format)',
    'indoor_temp_c': 'Indoor temperature in degrees Celsius (°C)',
    'hvac_kw': 'HVAC system power consumption in kilowatts (kW)',
    'occupancy_count': 'Number of occupants currently in the building',
    'camera_id': 'Unique identifier for CCTV camera (CAM-XXX format)',
    'date': 'Calendar date of observation/record (YYYY-MM-DD format)',
    'uptime_pct': 'Camera operational uptime as percentage of time period (0-100%)',
    'trip_id': 'Unique identifier for waste collection trip (TRP-XXXXX format)',
    'truck_id': 'Unique identifier for collection vehicle/truck (TRK-XX format)',
    'route_id': 'Unique identifier for assigned collection route (RXX format)',
    'start_time': 'Trip commencement timestamp',
    'end_time': 'Trip completion timestamp',
    'bins_collected': 'Number of bins emptied/collected during this trip',
    'tonnes': 'Total weight of collected waste in metric tonnes',
    'kwh': 'Electricity consumption in kilowatt-hours (kWh)',
    'service_type': 'Type/category of government service requested/delivered',
    'channel': 'Delivery/service channel (online, service_centre, call_centre, mobile_app, web)',
    'transactions': 'Number of transactions or service instances processed',
    'avg_processing_days': 'Average number of days to process/complete service',
    'incident_id': 'Unique identifier for security/public safety incident (INC-XXXXXX format)',
    'zone_id': 'City/district zone identifier (Z01-Z05 format)',
    'type': 'Classification/type of incident (suspicious_activity, illegal_parking, etc.)',
    'severity': 'Incident severity rating on scale 1-5 (1=minor, 5=critical)',
    'source': 'Origin/source of incident report (CCTV, citizen_report, sensor, patrol, etc.)',
    'response_min': 'Response time from report to action in minutes',
    'status': 'Current incident status (open, in_progress, closed, resolved)',
    'ingested_at': 'Timestamp when incident data was ingested into central system',
    'sensor_id': 'Unique identifier for sensor device (PRS-XX pressure, NSE-XX noise, TRF-XXX traffic)',
    'pressure_bar': 'Water pressure in bar (metric unit)',
    'flow_lps': 'Water flow rate in liters per second (L/s)',
    'laeq_db': 'A-weighted equivalent continuous sound pressure level in decibels (dBA)',
    'ticket_id': 'Unique identifier for operations ticket (OPS-XXXXXX format)',
    'created_at': 'Ticket creation/opening timestamp',
    'pillar': 'City management pillar/domain (energy, mobility, waste, water, safety, etc.)',
    'escalated': 'Boolean flag indicating if ticket was escalated (True/False)',
    'escalated_to_role': 'Target role/team ticket was escalated to (if escalated)',
    'resolved_at': 'Ticket resolution/completion timestamp',
    'handover_note': 'Notes or comments from escalation/handover process',
    'lot_id': 'Unique identifier for parking lot/area (LOT-XX format)',
    'capacity': 'Total number of parking spaces available in lot',
    'occupied': 'Number of parking spaces currently occupied',
    'request_id': 'Unique identifier for citizen service request (SR-XXXXXX format)',
    'category': 'Service request category/classification',
    'description_ar': 'Detailed description of request in Arabic language',
    'closed_at': 'Request closure/completion timestamp',
    'satisfaction_1_5': 'Citizen satisfaction rating on scale 1-5 (1=unsatisfied, 5=very satisfied)',
    'source_system': 'Originating system/application (CRM, mobile_app, web_portal, etc.)',
    'asset_id': 'Unique identifier for physical asset (SL-XXXX streetlight, TSG-XX traffic signal, CAM-XXX camera)',
    'burn_hours': 'Daily operating/burn hours for streetlight (hours per day)',
    'vehicle_count': 'Number of vehicles detected/passing during measurement interval',
    'avg_speed_kmh': 'Average speed of vehicles in kilometers per hour (km/h)',
    'occupancy_pct': 'Road/lane occupancy percentage during measurement interval',
    'line_id': 'Public transit route/line identifier (e.g., Line A, Line B)',
    'stop_id': 'Transit stop/station identifier (e.g., A01, B01)',
    'boardings': 'Number of passengers boarding at this stop during period',
    'alightings': 'Number of passengers alighting at this stop during period',
    'on_time_pct': 'On-time performance percentage for departures/arrivals',
    'm3': 'Water consumption volume in cubic meters (m³)',
    'chlorine_mg_l': 'Free chlorine concentration in milligrams per liter (mg/L)',
    'turbidity_ntu': 'Water turbidity in Nephelometric Turbidity Units (NTU)',
    'ph': 'Acidity/alkalinity level on pH scale (0-14, 7 = neutral)',
    'work_order_id': 'Unique identifier for maintenance work order (WO-XXXXX format)',
    'opened_at': 'Work order creation/opening timestamp',
    'category': 'Work order classification (Traffic signal, Streetlight, Infrastructure, etc.)',
    'priority': 'Work order priority level (P1=highest, P4=lowest)',
    'sla_hours': 'Service Level Agreement target completion time in hours'
}

table_desc = {
    'air_quality': 'Environmental monitoring data capturing air pollutant concentrations (PM2.5, PM10, NO2, O3) and meteorological conditions at air quality stations throughout the city.',
    'bin_fill': 'Real-time smart waste bin monitoring data tracking fill levels and temperature to optimize collection routes and prevent overflow.',
    'bms_readings': 'Building Management System telemetry providing indoor environmental conditions, HVAC energy consumption, and occupancy data for managed buildings.',
    'camera_status': 'CCTV infrastructure health monitoring tracking camera uptime and operational status across the surveillance network.',
    'collection_trips': 'Waste collection operation records detailing truck routes, trip schedules, number of bins collected, and total waste tonnage.',
    'electricity_meters': 'Building-level electricity consumption readings for energy monitoring, billing, and load analysis.',
    'gov_services': 'Aggregated government service delivery metrics tracking transaction volumes and processing times by service type and channel.',
    'incidents': 'Security and public safety incident records including location (zone), type, severity, source, response times, and resolution status.',
    'network_pressure': 'Water distribution network monitoring capturing pressure and flow rates at key sensor points to detect leaks and ensure service quality.',
    'noise': 'Environmental noise level monitoring providing equivalent continuous sound levels across different city locations.',
    'ops_tickets': 'Centralized operations ticketing system tracking issues across city pillars with escalation workflows and resolution tracking.',
    'parking_occupancy': 'Real-time parking lot occupancy monitoring showing capacity utilization across parking facilities.',
    'service_requests': 'Citizen service requests (311 system) submitted via multiple channels with Arabic descriptions, tracking, and satisfaction ratings.',
    'streetlights': 'Street lighting infrastructure monitoring including operational status and daily burn hours for maintenance planning.',
    'traffic_counts': 'Traffic flow monitoring capturing vehicle counts, average speeds, and road occupancy at sensor locations.',
    'transit_ridership': 'Public transportation ridership data showing boardings, alightings, and on-time performance by route and stop.',
    'water_meters': 'Building-level water consumption readings for usage monitoring and conservation analysis.',
    'water_quality': 'Drinking water quality monitoring at treatment/distribution stations tracking chlorine, turbidity, and pH levels.',
    'work_orders': 'Maintenance work order records for city assets including categorization, priority, SLA tracking, and completion status.'
}

content = []
content.append("# ERD - 4th Generation Town Dataset (Comprehensive Data Dictionary)\n\n")
content.append("**Source:** `01_CLEAN_SOURCE_CSV/` (19 CSV files, 2025 data)  \n")
content.append("**Cleaned Data:** `Code/data set/after process/` (duplicates removed, missing values imputed where logical)  \n")
content.append("**Purpose:** Complete schema documentation with detailed descriptions of every table, column, and relationship for analysis and dashboard development.\n\n")

content.append("## Table of Contents\n\n")
content.append("- [Dataset Overview](#dataset-overview)\n")
content.append("- [Complete Data Dictionary](#complete-data-dictionary)\n")
content.append("- [Entity Relationships](#entity-relationships)\n")
content.append("- [Enhanced Mermaid ERD](#enhanced-mermaid-erd)\n")
content.append("- [Data Usage Guidelines](#data-usage-guidelines)\n\n")

content.append("## Dataset Overview\n\n")
content.append("| Table | Description | Records | Time Granularity | Primary Use Case |\n")
content.append("|---|---|---|---|---|\n")
for name in sorted(tables.keys()):
    df = tables[name]
    # determine granularity
    if 'timestamp' in df.columns:
        gran = "Time-series (timestamp)"
    elif 'date' in df.columns:
        gran = "Daily (date)"
    elif 'start_time' in df.columns:
        gran = "Event-based (trip)"
    else:
        gran = "Aggregated"
    content.append(f"| `{name}` | {table_desc.get(name,'')} | {len(df):,} | {gran} | {table_desc.get(name,'').split('.')[0]} |\n")

content.append("\n## Complete Data Dictionary\n\n")
content.append("This section provides detailed information for every column in every table, including data types, descriptions, and sample values.\n\n")

for name in sorted(tables.keys()):
    df = tables[name]
    content.append(f"### {name.upper().replace('_',' ')} (`{name}.csv`)\n\n")
    content.append(f"**Description:** {table_desc.get(name,'')}\n\n")
    content.append(f"**Dimensions:** {df.shape[0]:,} rows × {df.shape[1]} columns\n\n")
    content.append(f"**Composite/Primary Key (inferred):** ")
    # infer key
    if 'timestamp' in df.columns and df.columns[0] not in ['timestamp','date']:
        content.append(f"({df.columns[0]}, {df.columns[1] if len(df.columns)>1 and df.columns[1] in ['timestamp','date'] else 'timestamp'})\n\n")
    elif 'date' in df.columns and df.columns[0] not in ['date']:
        content.append(f"({df.columns[0]}, {df.columns[1]})\n\n")
    elif name in ['incidents','ops_tickets','work_orders','collection_trips','service_requests']:
        pk = df.columns[0]
        content.append(f"{pk} (unique)\n\n")
    else:
        content.append(f"Composite key inferred\n\n")
    
    content.append("| Column | Data Type | Description | Business Meaning | Sample Values |\n")
    content.append("|---|---|---|---|---|\n")
    for col in df.columns:
        dtype = str(df[col].dtype)
        desc = col_desc.get(col, f"{col.replace('_', ' ').replace('ar','(Arabic)').title()} field")
        # business meaning
        biz = desc.split(' - ')[0] if ' - ' in desc else desc
        samples = df[col].dropna().unique()[:3]
        sample_str = ', '.join([str(s)[:40] for s in samples]) if len(samples) > 0 else 'N/A'
        content.append(f"| `{col}` | {dtype} | {desc} | {biz} | {sample_str} |\n")
    content.append("\n---\n\n")

content.append("## Entity Relationships\n\n")
content.append("### Logical Relationships (Inferred)\n\n")
content.append("The following relationships are inferred from shared identifier patterns. No explicit foreign key constraints exist in the source CSV files.\n\n")
content.append("| Relationship | Type | Join Condition | Description |\n")
content.append("|---|---|---|---|\n")
content.append("| incidents ↔ service_requests | Many-to-Many (Logical) | `incidents.zone_id = service_requests.zone_id` AND temporal proximity | Both relate to issues/events within the same geographic zone; can be correlated for comprehensive city insights |\n")
content.append("| bms_readings ↔ electricity_meters | One-to-One (by building/time) | `bms_readings.building_id = electricity_meters.building_id` AND `bms_readings.timestamp = electricity_meters.timestamp` | Combined view of building energy consumption with HVAC and occupancy context |\n")
content.append("| bms_readings ↔ water_meters | One-to-One (by building/time) | `bms_readings.building_id = water_meters.building_id` AND `bms_readings.timestamp = water_meters.timestamp` | Combined view of building water consumption with environmental conditions |\n")
content.append("| work_orders ↔ streetlights | Many-to-One | `work_orders.asset_id = streetlights.asset_id` | Maintenance history for streetlight assets (asset_id starts with SL-) |\n")
content.append("| work_orders ↔ camera_status | Many-to-One (Possible) | `work_orders.asset_id = camera_status.camera_id` | Maintenance history for CCTV assets (asset_id starts with CAM-) |\n")
content.append("| collection_trips ↔ bin_fill | Many-to-Many (Logical) | Via `truck_id`/`route_id` and time windows | Collection trips service bins along assigned routes; no direct trip-bin junction table exists |\n")
content.append("| ops_tickets ↔ work_orders/service_requests | Many-to-Many (Correlated) | Temporal and categorical correlation | Operations tickets may relate to work orders or service requests for coordination |\n\n")

content.append("### Shared Dimensions\n\n")
content.append("| Dimension | Source Tables | Purpose |\n")
content.append("|---|---|---|\n")
content.append("| **Zone** (`zone_id`: Z01-Z05) | `incidents`, `service_requests` | Geographic zones for spatial analysis and service delivery tracking |\n")
content.append("| **Building** (`building_id`: B-XXXX) | `bms_readings`, `electricity_meters`, `water_meters` | Building-level utility consumption and environmental monitoring |\n")
content.append("| **Asset** (`asset_id`: SL-XXXX, TSG-XX, CAM-XXX) | `streetlights`, `work_orders` | Physical city infrastructure assets requiring maintenance |\n")
content.append("| **Sensor/Station** (various prefixes) | `air_quality`(AQ-), `noise`(NSE-), `network_pressure`(PRS-), `traffic_counts`(TRF-), `water_quality`(WQ-) | Environmental and infrastructure monitoring points |\n")
content.append("| **Time** (timestamp/date) | All time-series tables | Temporal dimension for trend analysis and reporting |\n\n")

content.append("## Enhanced Mermaid ERD\n\n")
content.append("```mermaid\nerDiagram\n    AIR_QUALITY {\n        string station_id PK \"Monitoring station (AQ-XX)\"\n        datetime timestamp PK \"Measurement time\"\n        float pm25 \"PM2.5 (μg/m³)\"\n        float pm10 \"PM10 (μg/m³)\"\n        float no2 \"NO2 concentration\"\n        float o3 \"Ozone concentration\"\n        float temp_c \"Temperature (°C)\"\n        float humidity_pct \"Humidity (%)\"\n    }\n    \n    BIN_FILL {\n        string bin_id PK \"Smart bin (BIN-XXX)\"\n        datetime timestamp PK \"Reading time\"\n        float fill_pct \"Fill level (%)\"\n        float temp_c \"Bin temperature (°C)\"\n    }\n    \n    BMS_READINGS {\n        string building_id PK \"Building (B-XXXX)\"\n        datetime timestamp PK \"Reading time\"\n        float indoor_temp_c \"Indoor temp (°C)\"\n        float humidity_pct \"Humidity (%)\"\n        float hvac_kw \"HVAC power (kW)\"\n        int occupancy_count \"Occupants\"\n    }\n    \n    CAMERA_STATUS {\n        string camera_id PK \"Camera (CAM-XXX)\"\n        date date PK \"Date\"\n        float uptime_pct \"Uptime (%)\"\n    }\n    \n    COLLECTION_TRIPS {\n        string trip_id PK \"Trip (TRP-XXXXX)\"\n        string truck_id \"Truck (TRK-XX)\"\n        string route_id \"Route (RXX)\"\n        datetime start_time \"Start time\"\n        datetime end_time \"End time\"\n        int bins_collected \"Bins collected\"\n        float tonnes \"Waste (tonnes)\"\n    }\n    \n    ELECTRICITY_METERS {\n        string building_id PK \"Building (B-XXXX)\"\n        datetime timestamp PK \"Reading time\"\n        float kwh \"Consumption (kWh)\"\n    }\n    \n    GOV_SERVICES {\n        date date PK \"Date\"\n        string service_type PK \"Service type\"\n        string channel PK \"Channel\"\n        int transactions \"Transactions\"\n        float avg_processing_days \"Avg processing (days)\"\n    }\n    \n    INCIDENTS {\n        string incident_id PK \"Incident (INC-XXXXXX)\"\n        datetime timestamp \"Incident time\"\n        string zone_id \"Zone (Z01-Z05)\"\n        string type \"Incident type\"\n        int severity \"Severity (1-5)\"\n        string source \"Source\"\n        float response_min \"Response (min)\"\n        string status \"Status\"\n        datetime ingested_at \"Ingest time\"\n    }\n    \n    NETWORK_PRESSURE {\n        string sensor_id PK \"Sensor (PRS-XX)\"\n        datetime timestamp PK \"Reading time\"\n        float pressure_bar \"Pressure (bar)\"\n        float flow_lps \"Flow (L/s)\"\n    }\n    \n    NOISE {\n        string sensor_id PK \"Sensor (NSE-XX)\"\n        datetime timestamp PK \"Reading time\"\n        float laeq_db \"Noise (dBA)\"\n    }\n    \n    OPS_TICKETS {\n        string ticket_id PK \"Ticket (OPS-XXXXXX)\"\n        datetime created_at \"Created\"\n        string pillar \"City pillar\"\n        string source \"Source\"\n        int severity \"Severity\"\n        string status \"Status\"\n        boolean escalated \"Escalated\"\n        string escalated_to_role \"Escalated to\"\n        datetime resolved_at \"Resolved\"\n        string handover_note \"Notes\"\n    }\n    \n    PARKING_OCCUPANCY {\n        string lot_id PK \"Lot (LOT-XX)\"\n        datetime timestamp PK \"Reading time\"\n        int capacity \"Total spaces\"\n        int occupied \"Occupied spaces\"\n    }\n    \n    SERVICE_REQUESTS {\n        string request_id PK \"Request (SR-XXXXXX)\"\n        datetime created_at \"Created\"\n        string channel \"Channel\"\n        string category \"Category\"\n        string zone_id \"Zone (Z01-Z05)\"\n        string description_ar \"Description (Arabic)\"\n        string status \"Status\"\n        datetime closed_at \"Closed\"\n        float satisfaction_1_5 \"Satisfaction (1-5)\"\n        string source_system \"Source system\"\n    }\n    \n    STREETLIGHTS {\n        string asset_id PK \"Asset (SL-XXXX)\"\n        date date PK \"Date\"\n        string status \"Status\"\n        float burn_hours \"Burn hours\"\n    }\n    \n    TRAFFIC_COUNTS {\n        string sensor_id PK \"Sensor (TRF-XXX)\"\n        datetime timestamp PK \"Reading time\"\n        int vehicle_count \"Vehicles\"\n        float avg_speed_kmh \"Avg speed (km/h)\"\n        float occupancy_pct \"Occupancy (%)\"\n    }\n    \n    TRANSIT_RIDERSHIP {\n        date date PK \"Date\"\n        string line_id PK \"Line\"\n        string stop_id PK \"Stop\"\n        int boardings \"Boardings\"\n        int alightings \"Alightings\"\n        float on_time_pct \"On-time (%)\"\n    }\n    \n    WATER_METERS {\n        string building_id PK \"Building (B-XXXX)\"\n        datetime timestamp PK \"Reading time\"\n        float m3 \"Consumption (m³)\"\n    }\n    \n    WATER_QUALITY {\n        string station_id PK \"Station (WQ-XX)\"\n        date date PK \"Date\"\n        float chlorine_mg_l \"Chlorine (mg/L)\"\n        float turbidity_ntu \"Turbidity (NTU)\"\n        float ph \"pH\"\n    }\n    \n    WORK_ORDERS {\n        string work_order_id PK \"WO (WO-XXXXX)\"\n        string asset_id \"Asset ID\"\n        datetime opened_at \"Opened\"\n        datetime closed_at \"Closed\"\n        string category \"Category\"\n        string priority \"Priority (P1-P4)\"\n        int sla_hours \"SLA (hours)\"\n        string status \"Status\"\n    }\n    \n    SERVICE_REQUESTS ||--o{ INCIDENTS : \"zone correlation\"\n    WORK_ORDERS }o--|| STREETLIGHTS : \"asset maintenance\"\n    WORK_ORDERS }o--|| CAMERA_STATUS : \"asset maintenance\"\n    BMS_READINGS ||--|| ELECTRICITY_METERS : \"building utilities\"\n    BMS_READINGS ||--|| WATER_METERS : \"building utilities\"\n    COLLECTION_TRIPS ||--o{ BIN_FILL : \"route service\"\n```\n\n## Data Usage Guidelines\n\n### Data Quality Notes\n- **Cleaned Data Available:** Use files from `Code/data set/after process/` which have duplicates removed and missing values imputed (forward-fill/backward-fill) for time-series data where logically appropriate\n- **Timestamps:** Many include timezone offsets (+02:00). Cleaned versions may be normalized to naive datetimes\n- **Arabic Content:** `service_requests.description_ar` contains Arabic text - ensure proper UTF-8 encoding when processing\n- **Missing Values:** Some fields may have nulls (e.g., `satisfaction_1_5` only filled when survey completed, `escalated_to_role` only when escalated)\n\n### Analysis Recommendations\n- **Time Series:** Most sensor data is time-indexed - use proper datetime parsing and consider resampling for analysis\n- **Spatial Analysis:** Use `zone_id` for incidents/service requests; building/sensor IDs for location mapping\n- **Performance Metrics:** Calculate KPIs using `response_min`, `avg_processing_days`, `on_time_pct`, etc.\n- **Correlations:** Leverage shared keys (zone_id, building_id, asset_id) to join related datasets\n- **Data Volume:** Large tables like `electricity_meters`, `water_meters`, `traffic_counts`, `bin_fill` require efficient processing (consider sampling or aggregation)\n\n### File Locations\n- **Original Clean Source:** `01_CLEAN_SOURCE_CSV/`\n- **Cleaned & Processed:** `Code/data set/after process/`\n- **Dimensions:** Available in `Code/data set/after process/dim_*.csv` (calendar, zone, building, asset, sensor)\n- **Dashboards:** `Code/dashboards/`\n")

out_path = r"C:\Users\abdel\OneDrive\Desktop\ACUD\Moamen\Oasis_READY_CLEAN_DATA_v4\Oasis_READY_CLEAN_DATA_v4\ERD_4th_Gen_Town.md"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(''.join(content))

print(f"Enhanced ERD written to {out_path}")
print(f"Total tables documented: {len(tables)}")
