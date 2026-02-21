-- UK Water Pollution Observatory — Database Schema
-- PostgreSQL 17 + PostGIS
--
-- Usage: psql -d water_quality -f schema.sql
--
-- This file is the canonical schema definition.
-- Dumped from the live database and maintained in version control.

-- ============================================================
-- Extensions
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

-- ============================================================
-- Core tables
-- ============================================================

-- Provenance: every ingestion run creates a source row.
CREATE TABLE public.sources (
    source_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    provider text NOT NULL,
    dataset_name text NOT NULL,
    source_url text NOT NULL,
    license text NOT NULL,
    fetched_at timestamp with time zone NOT NULL,
    raw_metadata jsonb,
    -- Legacy columns (retained for backward compatibility)
    organisation text,
    dataset text,
    url text,
    licence text,
    meta jsonb
);

-- Bathing water sites (and potentially other site types).
CREATE TABLE public.sites (
    site_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    site_type text NOT NULL,
    name text NOT NULL,
    location public.geometry(Point,4326) NOT NULL,
    waterbody_name text,
    catchment_name text,
    source_id uuid,
    raw_metadata jsonb,
    -- EA bathing water enrichment columns
    eubwid text,
    sampling_point_id text,
    sampling_point_url text,
    latest_profile_url text,
    latest_sample_assessment_url text,
    latest_risk_prediction_url text,
    latest_risk_expires_at timestamp with time zone,
    latest_risk_level text,
    latest_risk_url text,
    risk_status text,
    risk_staleness_hours numeric,
    risk_freshness text
);

-- Lab sample values linked to sites.
CREATE TABLE public.samples (
    sample_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    site_id uuid,
    sample_date date NOT NULL,
    parameter text NOT NULL,
    value numeric,
    unit text,
    source_id uuid,
    raw_metadata jsonb
);

-- EA flood monitoring + hydrology stations.
CREATE TABLE public.stations (
    station_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    station_reference text NOT NULL,
    label text NOT NULL,
    river_name text,
    catchment_name text,
    location public.geometry(Point,4326) NOT NULL,
    source_id uuid,
    raw_metadata jsonb
);

-- Measures associated with stations.
CREATE TABLE public.measures (
    measure_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    station_id uuid,
    measure_ref text NOT NULL,
    parameter text NOT NULL,
    parameter_name text,
    unit_name text,
    period_seconds integer,
    qualifier text,
    raw_metadata jsonb
);

-- Storm overflow assets (EDM annual return).
CREATE TABLE public.overflows (
    overflow_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    unique_id text NOT NULL,
    water_company_name text NOT NULL,
    site_name_ea text,
    site_name_wasc text,
    ea_permit_reference text,
    activity_reference text,
    asset_type text,
    outlet_discharge_ngr text,
    wfd_waterbody_id text,
    wfd_catchment_name text,
    receiving_water_name text,
    source_id uuid,
    raw_metadata jsonb,
    location public.geometry(Point,27700),
    -- Phase 3 Q4 normalisation columns
    receiving_water_canonical text,
    receiving_water_tidal boolean,
    receiving_water_semantic text,
    -- Phase 4 impact tier
    impact_tier text
);

-- Annual return data per overflow per year.
CREATE TABLE public.overflow_annual_returns (
    return_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    unique_id text NOT NULL,
    report_year integer NOT NULL,
    data_start_year integer,
    edm_operational_pct numeric,
    total_duration_text text,
    counted_spills integer,
    long_term_avg_spill_count numeric,
    source_id uuid,
    raw_metadata jsonb
);

-- Defra Water Recreation Locations (unofficial swim spots).
CREATE TABLE public.recreation_sites (
    rec_site_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    location_id text NOT NULL,
    location public.geometry(Point,4326) NOT NULL,
    waterbody_salinity text,
    waterbody_type text,
    recreation_types text,
    num_reports integer,
    num_data_sources integer,
    num_recreation_types integer,
    swimming boolean DEFAULT false,
    paddling boolean DEFAULT false,
    rowing boolean DEFAULT false,
    sailing boolean DEFAULT false,
    surfing boolean DEFAULT false,
    easting numeric,
    northing numeric,
    source_id uuid,
    raw_properties jsonb,
    near_designated_bathing boolean DEFAULT false
);

-- EA WIMS water quality sampling point locations.
CREATE TABLE public.wq_sampling_points (
    sp_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    notation text NOT NULL,
    label text,
    sp_status text,
    sp_type text,
    region text,
    area text,
    sub_area text,
    location public.geometry(Point,4326) NOT NULL,
    source_id uuid,
    raw_properties jsonb
);

-- ============================================================
-- Reference / lookup tables
-- ============================================================

CREATE TABLE public.receiving_water_aliases (
    alias text NOT NULL,
    canonical text NOT NULL,
    notes text
);

CREATE TABLE public.receiving_water_normalisation (
    raw_name text NOT NULL,
    canonical_name text NOT NULL
);

CREATE TABLE public.bathing_seasons (
    year integer NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    notes text
);

CREATE TABLE public.site_bathing_seasons (
    site_id uuid NOT NULL,
    season_year integer NOT NULL
);

-- ============================================================
-- Analysis snapshot tables (Phase 4 — Wallingford case study)
-- ============================================================

CREATE TABLE public.q4_wallingford_impact_summary (
    impact_tier text,
    overflow_count bigint
);

CREATE TABLE public.q4_wallingford_overflows_within_10km (
    overflow_id uuid,
    unique_id text,
    site_name_ea text,
    receiving_water_name text,
    receiving_water_canonical text,
    receiving_water_semantic text,
    tidal_flag boolean,
    site_id uuid,
    distance_m integer
);

CREATE TABLE public.q4_wallingford_q2_single_date (
    bathing_site text,
    sample_date date,
    parameter text,
    value numeric,
    unique_id text,
    site_name_ea text,
    receiving_water_semantic text,
    tidal_flag boolean,
    distance_m integer,
    counted_spills integer,
    long_term_avg_spill_count numeric,
    edm_operational_pct numeric,
    total_duration_text text
);

CREATE TABLE public.q4_wallingford_q2_summary (
    bathing_site text,
    sample_date date,
    parameter text,
    value numeric,
    nearby_overflow_assets bigint,
    nearest_overflow_m integer,
    assets_within_2km bigint,
    assets_within_10km bigint,
    total_counted_spills_nearby bigint,
    total_duration_seconds_nearby bigint,
    avg_edm_operational_pct_nearby numeric
);

CREATE TABLE public.q4_wallingford_snapshot (
    snap_ts timestamp without time zone,
    overflow_id uuid,
    unique_id text,
    site_name_ea text,
    receiving_water_name text,
    receiving_water_canonical text,
    receiving_water_semantic text,
    tidal_flag boolean,
    site_id uuid,
    distance_m integer,
    impact_tier text
);

CREATE TABLE public.q4_wallingford_tier_c_overflows (
    overflow_id uuid,
    unique_id text,
    site_name_ea text,
    receiving_water_name text,
    receiving_water_canonical text,
    receiving_water_semantic text,
    tidal_flag boolean,
    site_id uuid,
    distance_m integer
);

-- ============================================================
-- Views
-- ============================================================

CREATE VIEW public.v_bathing_water_latest_quality AS
 SELECT s.site_id,
    s.name AS bathing_water,
    max(sa.sample_date) AS latest_sample_date,
    max(sa.value) FILTER (WHERE (sa.parameter = 'escherichia_coli'::text)) AS e_coli_cfu_100ml,
    max(sa.value) FILTER (WHERE (sa.parameter = 'intestinal_enterococci'::text)) AS enterococci_cfu_100ml
   FROM (public.sites s
     JOIN public.samples sa ON ((sa.site_id = s.site_id)))
  WHERE (s.site_type = 'bathing_water'::text)
  GROUP BY s.site_id, s.name;

CREATE VIEW public.v_bathing_water_latest_sample AS
 SELECT s.site_id,
    s.name,
    s.eubwid,
    max(sa.sample_date) AS latest_sample_date,
    max(sa.value) FILTER (WHERE (sa.parameter = 'escherichia_coli'::text)) AS ecoli_cfu_100ml,
    max(sa.value) FILTER (WHERE (sa.parameter = 'intestinal_enterococci'::text)) AS enterococci_cfu_100ml,
    s.latest_risk_level,
    s.latest_risk_expires_at,
    s.risk_status,
    s.risk_staleness_hours
   FROM (public.sites s
     LEFT JOIN public.samples sa ON ((sa.site_id = s.site_id)))
  WHERE (s.site_type = 'bathing_water'::text)
  GROUP BY s.site_id, s.name, s.eubwid, s.latest_risk_level, s.latest_risk_expires_at, s.risk_status, s.risk_staleness_hours;

CREATE VIEW public.v_bathing_water_public_status AS
 SELECT site_id,
    name,
    eubwid,
    latest_risk_level,
    latest_risk_expires_at,
        CASE
            WHEN (latest_risk_expires_at IS NULL) THEN 'unknown'::text
            WHEN (latest_risk_expires_at < now()) THEN 'expired'::text
            ELSE 'current'::text
        END AS risk_status,
    (now() - latest_risk_expires_at) AS risk_staleness,
    latest_risk_url
   FROM public.sites s
  WHERE (site_type = 'bathing_water'::text);

CREATE VIEW public.v_overflow_bathing_distances AS
 SELECT s.site_id,
    s.name AS bathing_site_name,
    o.overflow_id,
    o.unique_id,
    o.site_name_ea,
    o.receiving_water_name,
    o.receiving_water_canonical,
    o.receiving_water_semantic,
    o.receiving_water_tidal AS tidal_flag,
    (round(public.st_distance(o.location, public.st_transform(s.location, 27700))))::integer AS distance_m
   FROM (public.sites s
     JOIN public.overflows o ON ((s.site_type = 'bathing_water'::text)))
  WHERE ((s.location IS NOT NULL) AND (o.location IS NOT NULL));

-- ============================================================
-- Primary keys
-- ============================================================

ALTER TABLE ONLY public.sources ADD CONSTRAINT sources_pkey PRIMARY KEY (source_id);
ALTER TABLE ONLY public.sites ADD CONSTRAINT sites_pkey PRIMARY KEY (site_id);
ALTER TABLE ONLY public.samples ADD CONSTRAINT samples_pkey PRIMARY KEY (sample_id);
ALTER TABLE ONLY public.stations ADD CONSTRAINT stations_pkey PRIMARY KEY (station_id);
ALTER TABLE ONLY public.measures ADD CONSTRAINT measures_pkey PRIMARY KEY (measure_id);
ALTER TABLE ONLY public.overflows ADD CONSTRAINT overflows_pkey PRIMARY KEY (overflow_id);
ALTER TABLE ONLY public.overflow_annual_returns ADD CONSTRAINT overflow_annual_returns_pkey PRIMARY KEY (return_id);
ALTER TABLE ONLY public.bathing_seasons ADD CONSTRAINT bathing_seasons_pkey PRIMARY KEY (year);
ALTER TABLE ONLY public.site_bathing_seasons ADD CONSTRAINT site_bathing_seasons_pkey PRIMARY KEY (site_id, season_year);
ALTER TABLE ONLY public.receiving_water_aliases ADD CONSTRAINT receiving_water_aliases_pkey PRIMARY KEY (alias);
ALTER TABLE ONLY public.receiving_water_normalisation ADD CONSTRAINT receiving_water_normalisation_pkey PRIMARY KEY (raw_name);
ALTER TABLE ONLY public.recreation_sites ADD CONSTRAINT recreation_sites_pkey PRIMARY KEY (rec_site_id);
ALTER TABLE ONLY public.wq_sampling_points ADD CONSTRAINT wq_sampling_points_pkey PRIMARY KEY (sp_id);

-- ============================================================
-- Unique constraints (natural keys for idempotent ingestion)
-- ============================================================

ALTER TABLE ONLY public.sites ADD CONSTRAINT sites_unique_name UNIQUE (name);
ALTER TABLE ONLY public.samples ADD CONSTRAINT samples_unique_site_date_param UNIQUE (site_id, sample_date, parameter);
ALTER TABLE ONLY public.stations ADD CONSTRAINT stations_station_reference_key UNIQUE (station_reference);
ALTER TABLE ONLY public.measures ADD CONSTRAINT measures_measure_ref_key UNIQUE (measure_ref);
ALTER TABLE ONLY public.overflows ADD CONSTRAINT overflows_unique_id_key UNIQUE (unique_id);
ALTER TABLE ONLY public.overflow_annual_returns ADD CONSTRAINT overflow_annual_returns_unique_id_report_year_key UNIQUE (unique_id, report_year);
ALTER TABLE ONLY public.recreation_sites ADD CONSTRAINT recreation_sites_location_id_key UNIQUE (location_id);
ALTER TABLE ONLY public.wq_sampling_points ADD CONSTRAINT wq_sampling_points_notation_key UNIQUE (notation);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX samples_site_date_idx ON public.samples USING btree (site_id, sample_date);
CREATE UNIQUE INDEX sites_bathing_eubwid_uq ON public.sites USING btree (eubwid) WHERE (site_type = 'bathing_water'::text);
CREATE INDEX sites_location_idx ON public.sites USING gist (location);
CREATE INDEX stations_location_idx ON public.stations USING gist (location);
CREATE INDEX recreation_sites_location_idx ON public.recreation_sites USING gist (location);
CREATE INDEX wq_sampling_points_location_idx ON public.wq_sampling_points USING gist (location);

-- ============================================================
-- Foreign keys
-- ============================================================

ALTER TABLE ONLY public.sites ADD CONSTRAINT sites_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
ALTER TABLE ONLY public.samples ADD CONSTRAINT samples_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(site_id);
ALTER TABLE ONLY public.samples ADD CONSTRAINT samples_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
ALTER TABLE ONLY public.stations ADD CONSTRAINT stations_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
ALTER TABLE ONLY public.measures ADD CONSTRAINT measures_station_id_fkey FOREIGN KEY (station_id) REFERENCES public.stations(station_id);
ALTER TABLE ONLY public.overflows ADD CONSTRAINT overflows_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
ALTER TABLE ONLY public.overflow_annual_returns ADD CONSTRAINT overflow_annual_returns_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
ALTER TABLE ONLY public.overflow_annual_returns ADD CONSTRAINT overflow_annual_returns_unique_id_fkey FOREIGN KEY (unique_id) REFERENCES public.overflows(unique_id);
ALTER TABLE ONLY public.site_bathing_seasons ADD CONSTRAINT site_bathing_seasons_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(site_id);
ALTER TABLE ONLY public.recreation_sites ADD CONSTRAINT recreation_sites_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
ALTER TABLE ONLY public.wq_sampling_points ADD CONSTRAINT wq_sampling_points_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(source_id);
