-- Vela: Snowflake setup for the patient's life story, searched with Cortex Search.
--
-- Who runs it: the Snowflake account owner, in a Snowsight worksheet. Select it all and
-- "Run All". It's safe to run again: everything is IF NOT EXISTS.
-- Then copy the names at the bottom into backend/.env.
--
-- The backend uses the account owner's existing token (their decision, October 10, 2026: no
-- separate role or token for the app). That token can act as ACCOUNTADMIN, so keep backend/.env
-- out of commits, chats, and screenshots, and replace the token after the hackathon.
--
-- Region: the account is on Google Cloud us-east4, which runs Cortex Search directly with the
-- snowflake-arctic-embed models (checked October 10, 2026).

-- Objects are owned by SYSADMIN (the usual owner of databases and warehouses), so they can be
-- managed later without ACCOUNTADMIN
USE ROLE SYSADMIN;

-- A small warehouse just for this: it builds the search index and runs the app's inserts, and
-- suspends after a minute idle, so it only uses credits while working
CREATE WAREHOUSE IF NOT EXISTS VELA_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Vela: life story search refreshes and inserts';

CREATE DATABASE IF NOT EXISTS VELA COMMENT = 'Vela voice companion';
CREATE SCHEMA IF NOT EXISTS VELA.LIFE_STORY COMMENT = 'The patient''s life story, searched by the voice agent';

-- One short fact about the patient's past per row (see docs/memory-track.md, "How to write the
-- life story"). Never plans, appointments, or medicine: those are memories, in Tiger Data.
CREATE TABLE IF NOT EXISTS VELA.LIFE_STORY.PASSAGES (
  ID         VARCHAR       NOT NULL DEFAULT UUID_STRING(),
  PATIENT_ID VARCHAR       NOT NULL,                -- 'demo', as PATIENT_ID in backend/app/store.py
  TOPIC      VARCHAR       NOT NULL,                -- family, childhood, work, home, music, food, pets, friends
  PASSAGE    VARCHAR       NOT NULL,                -- 1-2 sentences, names rather than "she" or "he"
  PEOPLE     VARCHAR,                               -- names in it, comma separated: 'Anna, Mark'
  SAID_BY    VARCHAR       NOT NULL,                -- who it came from: 'Anna, daughter'
  SENSITIVE  BOOLEAN       NOT NULL DEFAULT FALSE,  -- the agent steers gently instead of repeating it
  CREATED_AT TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  CONSTRAINT PASSAGES_PK PRIMARY KEY (ID)          -- informational: Snowflake doesn't enforce it
);

-- The search service refreshes incrementally, which needs change tracking. Snowflake tries to turn
-- it on by itself; this makes sure (and must be repeated if the table is ever recreated)
ALTER TABLE VELA.LIFE_STORY.PASSAGES SET CHANGE_TRACKING = TRUE;

-- Searches PASSAGE by meaning. PATIENT_ID and TOPIC can filter results. A new passage becomes
-- searchable within TARGET_LAG. EMBEDDING_MODEL can't be changed later: to change it, or any
-- setting here, use CREATE OR REPLACE instead of IF NOT EXISTS (the two can't be combined)
CREATE CORTEX SEARCH SERVICE IF NOT EXISTS VELA.LIFE_STORY.PASSAGE_SEARCH
  ON PASSAGE
  ATTRIBUTES PATIENT_ID, TOPIC
  WAREHOUSE = VELA_WH
  TARGET_LAG = '5 minutes'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-m-v1.5'
  COMMENT = 'Vela: the agent''s search_life_story tool'
  AS (
    SELECT ID, PATIENT_ID, TOPIC, PASSAGE, PEOPLE, SAID_BY, SENSITIVE
    FROM VELA.LIFE_STORY.PASSAGES
  );

-- Check: the service should be listed, and become ACTIVE once its first build finishes
SHOW CORTEX SEARCH SERVICES IN SCHEMA VELA.LIFE_STORY;

-- backend/.env (these names aren't secrets; SNOWFLAKE_PAT is):
-- SNOWFLAKE_WAREHOUSE=VELA_WH
-- SNOWFLAKE_DATABASE=VELA
-- SNOWFLAKE_SCHEMA=LIFE_STORY
-- SNOWFLAKE_SEARCH_SERVICE=PASSAGE_SEARCH
