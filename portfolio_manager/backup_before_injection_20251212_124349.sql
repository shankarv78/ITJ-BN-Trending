--
-- PostgreSQL database dump
--

\restrict 4PA2pAr2TTCa5MutpmQZYp7SbSQExvVsn0CH0aPn26GVulBU6egX73GU0asVdV0

-- Dumped from database version 14.20 (Homebrew)
-- Dumped by pg_dump version 14.20 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: portfolio_positions; Type: TABLE; Schema: public; Owner: pm_user
--

CREATE TABLE public.portfolio_positions (
    position_id character varying(50) NOT NULL,
    instrument character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    entry_timestamp timestamp without time zone NOT NULL,
    entry_price numeric(12,2) NOT NULL,
    lots integer NOT NULL,
    quantity integer NOT NULL,
    initial_stop numeric(12,2) NOT NULL,
    current_stop numeric(12,2) NOT NULL,
    highest_close numeric(12,2) NOT NULL,
    unrealized_pnl numeric(15,2) DEFAULT 0.0,
    realized_pnl numeric(15,2) DEFAULT 0.0,
    rollover_status character varying(20) DEFAULT 'none'::character varying,
    original_expiry character varying(20),
    original_strike integer,
    original_entry_price numeric(12,2),
    rollover_timestamp timestamp without time zone,
    rollover_pnl numeric(15,2) DEFAULT 0.0,
    rollover_count integer DEFAULT 0,
    strike integer,
    expiry character varying(20),
    pe_symbol character varying(50),
    ce_symbol character varying(50),
    pe_order_id character varying(50),
    ce_order_id character varying(50),
    pe_entry_price numeric(12,2),
    ce_entry_price numeric(12,2),
    contract_month character varying(20),
    futures_symbol character varying(50),
    futures_order_id character varying(50),
    atr numeric(12,2),
    limiter character varying(50),
    risk_contribution numeric(8,4),
    vol_contribution numeric(8,4),
    is_base_position boolean DEFAULT false,
    version integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    exit_timestamp timestamp without time zone,
    exit_price numeric(12,2),
    exit_reason character varying(50),
    is_test boolean DEFAULT false,
    original_lots integer,
    strategy_id integer DEFAULT 1,
    CONSTRAINT check_rollover_status CHECK (((rollover_status)::text = ANY ((ARRAY['none'::character varying, 'pending'::character varying, 'in_progress'::character varying, 'rolled'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT check_status CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'closed'::character varying, 'partial'::character varying])::text[])))
);


ALTER TABLE public.portfolio_positions OWNER TO pm_user;

--
-- Name: COLUMN portfolio_positions.is_test; Type: COMMENT; Schema: public; Owner: pm_user
--

COMMENT ON COLUMN public.portfolio_positions.is_test IS 'True if position was created in test mode (1 lot only)';


--
-- Name: COLUMN portfolio_positions.original_lots; Type: COMMENT; Schema: public; Owner: pm_user
--

COMMENT ON COLUMN public.portfolio_positions.original_lots IS 'Original calculated lots before test mode override (NULL if not test mode)';


--
-- Name: portfolio_state; Type: TABLE; Schema: public; Owner: pm_user
--

CREATE TABLE public.portfolio_state (
    id integer DEFAULT 1 NOT NULL,
    initial_capital numeric(15,2) NOT NULL,
    closed_equity numeric(15,2) NOT NULL,
    total_risk_amount numeric(15,2),
    total_risk_percent numeric(8,4),
    total_vol_amount numeric(15,2),
    margin_used numeric(15,2),
    version integer DEFAULT 1,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT single_row CHECK ((id = 1))
);


ALTER TABLE public.portfolio_state OWNER TO pm_user;

--
-- Name: pyramiding_state; Type: TABLE; Schema: public; Owner: pm_user
--

CREATE TABLE public.pyramiding_state (
    instrument character varying(20) NOT NULL,
    last_pyramid_price numeric(12,2),
    base_position_id character varying(50),
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.pyramiding_state OWNER TO pm_user;

--
-- Data for Name: portfolio_positions; Type: TABLE DATA; Schema: public; Owner: pm_user
--

COPY public.portfolio_positions (position_id, instrument, status, entry_timestamp, entry_price, lots, quantity, initial_stop, current_stop, highest_close, unrealized_pnl, realized_pnl, rollover_status, original_expiry, original_strike, original_entry_price, rollover_timestamp, rollover_pnl, rollover_count, strike, expiry, pe_symbol, ce_symbol, pe_order_id, ce_order_id, pe_entry_price, ce_entry_price, contract_month, futures_symbol, futures_order_id, atr, limiter, risk_contribution, vol_contribution, is_base_position, version, created_at, updated_at, exit_timestamp, exit_price, exit_reason, is_test, original_lots, strategy_id) FROM stdin;
GOLD_MINI_Long_1	GOLD_MINI	open	2025-12-11 14:36:23	129465.00	3	300	129192.84	129192.84	130368.00	0.00	0.00	none	\N	\N	\N	\N	0.00	0	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	332.60	\N	\N	\N	t	1	2025-12-11 22:15:49.870258	2025-12-11 22:15:49.870258	\N	\N	\N	f	\N	1
GOLD_MINI_Long_2	GOLD_MINI	open	2025-12-11 22:10:16	130368.00	1	100	129192.84	129192.84	130368.00	0.00	0.00	none	\N	\N	\N	\N	0.00	0	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	332.60	\N	\N	\N	f	1	2025-12-11 22:15:49.870258	2025-12-11 22:15:49.870258	\N	\N	\N	f	\N	1
GOLD_MINI_Long_3	GOLD_MINI	open	2025-12-12 03:30:00	130914.00	1	100	130430.36	130430.36	130805.00	0.00	0.00	none	\N	\N	\N	\N	0.00	0	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0.00	\N	0.0000	0.0000	f	1	2025-12-11 23:00:23.063508	2025-12-11 23:00:23.063508	\N	\N	\N	f	\N	1
GOLD_MINI_Long_4	GOLD_MINI	open	2025-12-12 15:30:00	131173.00	1	100	130605.66	130605.66	131011.00	0.00	0.00	none	\N	\N	\N	\N	0.00	0	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0.00	\N	0.0000	0.0000	f	1	2025-12-12 11:00:11.683107	2025-12-12 11:00:11.683107	\N	\N	\N	f	\N	1
\.


--
-- Data for Name: portfolio_state; Type: TABLE DATA; Schema: public; Owner: pm_user
--

COPY public.portfolio_state (id, initial_capital, closed_equity, total_risk_amount, total_risk_percent, total_vol_amount, margin_used, version, updated_at) FROM stdin;
\.


--
-- Data for Name: pyramiding_state; Type: TABLE DATA; Schema: public; Owner: pm_user
--

COPY public.pyramiding_state (instrument, last_pyramid_price, base_position_id, updated_at) FROM stdin;
GOLD_MINI	131011.00	GOLD_MINI_Long_1	2025-12-12 11:00:11.697608
\.


--
-- Name: portfolio_positions portfolio_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: pm_user
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_pkey PRIMARY KEY (position_id);


--
-- Name: portfolio_state portfolio_state_pkey; Type: CONSTRAINT; Schema: public; Owner: pm_user
--

ALTER TABLE ONLY public.portfolio_state
    ADD CONSTRAINT portfolio_state_pkey PRIMARY KEY (id);


--
-- Name: pyramiding_state pyramiding_state_pkey; Type: CONSTRAINT; Schema: public; Owner: pm_user
--

ALTER TABLE ONLY public.pyramiding_state
    ADD CONSTRAINT pyramiding_state_pkey PRIMARY KEY (instrument);


--
-- Name: idx_created_at; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_created_at ON public.portfolio_positions USING btree (created_at);


--
-- Name: idx_exit_timestamp; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_exit_timestamp ON public.portfolio_positions USING btree (exit_timestamp);


--
-- Name: idx_instrument_entry; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_instrument_entry ON public.portfolio_positions USING btree (instrument, entry_timestamp);


--
-- Name: idx_instrument_status; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_instrument_status ON public.portfolio_positions USING btree (instrument, status);


--
-- Name: idx_portfolio_positions_is_test; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_portfolio_positions_is_test ON public.portfolio_positions USING btree (is_test) WHERE (is_test = true);


--
-- Name: idx_position_strategy; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_position_strategy ON public.portfolio_positions USING btree (strategy_id);


--
-- Name: idx_position_strategy_status; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_position_strategy_status ON public.portfolio_positions USING btree (strategy_id, status);


--
-- Name: idx_rollover_status; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_rollover_status ON public.portfolio_positions USING btree (rollover_status, expiry);


--
-- Name: idx_status; Type: INDEX; Schema: public; Owner: pm_user
--

CREATE INDEX idx_status ON public.portfolio_positions USING btree (status);


--
-- Name: portfolio_positions position_delete_audit; Type: TRIGGER; Schema: public; Owner: pm_user
--

CREATE TRIGGER position_delete_audit BEFORE DELETE ON public.portfolio_positions FOR EACH ROW EXECUTE FUNCTION public.log_position_delete();


--
-- Name: portfolio_positions portfolio_positions_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pm_user
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.trading_strategies(strategy_id);


--
-- Name: pyramiding_state pyramiding_state_base_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pm_user
--

ALTER TABLE ONLY public.pyramiding_state
    ADD CONSTRAINT pyramiding_state_base_position_id_fkey FOREIGN KEY (base_position_id) REFERENCES public.portfolio_positions(position_id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict 4PA2pAr2TTCa5MutpmQZYp7SbSQExvVsn0CH0aPn26GVulBU6egX73GU0asVdV0
