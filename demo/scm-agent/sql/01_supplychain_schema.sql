-- SCM-Agent Suite 데모 데이터셋 — 수출 제조 중견기업(전자부품) 공급망
-- 마스터(그래프 인스턴스) : scm_supplier, scm_item, scm_customer, scm_contract, scm_purchase_order
-- 트랜잭션(가상 클래스)  : scm_po_line, scm_shipment, scm_customs_declaration,
--                         scm_inventory_daily, scm_customer_order, scm_claim_ticket
DROP SCHEMA IF EXISTS supplychain CASCADE;
CREATE SCHEMA supplychain;
SET search_path TO supplychain;

CREATE TABLE scm_supplier (
  supplier_id   VARCHAR(12) PRIMARY KEY,
  supplier_name VARCHAR(80) NOT NULL,
  country       VARCHAR(30) NOT NULL,
  city          VARCHAR(40),
  tier          SMALLINT NOT NULL,            -- 1차/2차 협력사
  category      VARCHAR(40) NOT NULL,         -- PCB, 커넥터, 반도체, 사출, 포장재 ...
  rating        NUMERIC(3,1),                 -- 공급사 평가점수 (0~5)
  avg_lead_days INTEGER,
  on_time_rate  NUMERIC(5,3),                 -- 최근 12개월 납기준수율
  incoterms     VARCHAR(5),
  currency      VARCHAR(3)
);

CREATE TABLE scm_item (
  item_id        VARCHAR(12) PRIMARY KEY,
  item_name      VARCHAR(80) NOT NULL,
  item_type      VARCHAR(20) NOT NULL,        -- RAW / SUB / FG
  hs_code        VARCHAR(10),                 -- 품목분류(HS 6~10자리)
  origin_country VARCHAR(30),
  unit           VARCHAR(8),
  std_cost_usd   NUMERIC(12,2),
  safety_stock   INTEGER,
  moq            INTEGER,
  primary_supplier_id VARCHAR(12) REFERENCES scm_supplier(supplier_id),
  alt_supplier_id     VARCHAR(12) REFERENCES scm_supplier(supplier_id)
);

CREATE TABLE scm_customer (
  customer_id   VARCHAR(12) PRIMARY KEY,
  customer_name VARCHAR(80) NOT NULL,
  country       VARCHAR(30) NOT NULL,
  segment       VARCHAR(30),                  -- 글로벌 OEM / ODM / 유통
  incoterms     VARCHAR(5),
  payment_terms VARCHAR(20),
  sla_days      INTEGER
);

CREATE TABLE scm_contract (
  contract_id   VARCHAR(14) PRIMARY KEY,
  supplier_id   VARCHAR(12) NOT NULL REFERENCES scm_supplier(supplier_id),
  contract_type VARCHAR(20) NOT NULL,         -- 단가계약 / 연간공급 / 품질보증
  start_date    DATE NOT NULL,
  end_date      DATE NOT NULL,
  auto_renew    BOOLEAN DEFAULT FALSE,
  penalty_rate  NUMERIC(5,2),                 -- 납기지연 페널티(%)
  price_lock    BOOLEAN DEFAULT FALSE,
  status        VARCHAR(12) NOT NULL,         -- ACTIVE / EXPIRING / EXPIRED
  risk_clause   VARCHAR(200)
);

CREATE TABLE scm_purchase_order (
  po_id         VARCHAR(14) PRIMARY KEY,
  supplier_id   VARCHAR(12) NOT NULL REFERENCES scm_supplier(supplier_id),
  contract_id   VARCHAR(14) REFERENCES scm_contract(contract_id),
  order_date    DATE NOT NULL,
  promised_date DATE NOT NULL,
  status        VARCHAR(14) NOT NULL,         -- OPEN / PARTIAL / RECEIVED / DELAYED / CANCELLED
  total_amount_usd NUMERIC(14,2),
  buyer         VARCHAR(30),
  priority      VARCHAR(8)                    -- HIGH / NORMAL
);

-- 트랜잭션 (가상 클래스 — 그래프에 복제하지 않는다)
CREATE TABLE scm_po_line (
  po_line_id    SERIAL PRIMARY KEY,
  po_id         VARCHAR(14) NOT NULL REFERENCES scm_purchase_order(po_id),
  item_id       VARCHAR(12) NOT NULL REFERENCES scm_item(item_id),
  qty_ordered   INTEGER NOT NULL,
  qty_received  INTEGER NOT NULL DEFAULT 0,
  unit_price_usd NUMERIC(12,4),
  line_status   VARCHAR(14)
);

CREATE TABLE scm_shipment (
  shipment_id   VARCHAR(14) PRIMARY KEY,
  po_id         VARCHAR(14) NOT NULL REFERENCES scm_purchase_order(po_id),
  supplier_id   VARCHAR(12) NOT NULL REFERENCES scm_supplier(supplier_id),
  mode          VARCHAR(8),                   -- SEA / AIR / TRUCK
  forwarder     VARCHAR(40),
  etd           DATE,
  eta           DATE,
  atd           DATE,
  ata           DATE,
  status        VARCHAR(16),                  -- BOOKED / IN_TRANSIT / CUSTOMS_HOLD / DELIVERED / DELAYED
  delay_days    INTEGER DEFAULT 0,
  delay_reason  VARCHAR(80),
  bl_no         VARCHAR(20)
);

CREATE TABLE scm_customs_declaration (
  decl_id        VARCHAR(16) PRIMARY KEY,
  shipment_id    VARCHAR(14) REFERENCES scm_shipment(shipment_id),
  direction      VARCHAR(6) NOT NULL,         -- IMPORT / EXPORT
  item_id        VARCHAR(12) NOT NULL REFERENCES scm_item(item_id),
  declared_hs_code VARCHAR(10),
  origin_country VARCHAR(30),
  fta_applied    BOOLEAN,
  coo_required   BOOLEAN,                     -- 원산지증명 필요 여부
  coo_attached   BOOLEAN,
  invoice_value_usd NUMERIC(14,2),
  duty_rate      NUMERIC(5,2),
  status         VARCHAR(16),                 -- DRAFT / FILED / CLEARED / HOLD / REJECTED
  hold_reason    VARCHAR(120),
  filed_date     DATE
);

CREATE TABLE scm_inventory_daily (
  snapshot_date DATE NOT NULL,
  item_id       VARCHAR(12) NOT NULL REFERENCES scm_item(item_id),
  warehouse     VARCHAR(10) NOT NULL,
  on_hand_qty   INTEGER NOT NULL,
  reserved_qty  INTEGER NOT NULL DEFAULT 0,
  in_transit_qty INTEGER NOT NULL DEFAULT 0,
  avg_daily_usage NUMERIC(10,2),
  PRIMARY KEY (snapshot_date, item_id, warehouse)
);

CREATE TABLE scm_customer_order (
  so_id         VARCHAR(14) PRIMARY KEY,
  customer_id   VARCHAR(12) NOT NULL REFERENCES scm_customer(customer_id),
  item_id       VARCHAR(12) NOT NULL REFERENCES scm_item(item_id),
  order_date    DATE NOT NULL,
  requested_date DATE NOT NULL,
  confirmed_date DATE,
  qty           INTEGER NOT NULL,
  status        VARCHAR(14),                  -- CONFIRMED / IN_PRODUCTION / SHIPPED / AT_RISK / DELIVERED
  risk_note     VARCHAR(120)
);

CREATE TABLE scm_claim_ticket (
  ticket_id     VARCHAR(14) PRIMARY KEY,
  customer_id   VARCHAR(12) NOT NULL REFERENCES scm_customer(customer_id),
  so_id         VARCHAR(14) REFERENCES scm_customer_order(so_id),
  item_id       VARCHAR(12) REFERENCES scm_item(item_id),
  opened_date   DATE NOT NULL,
  category      VARCHAR(20),                  -- 납기문의 / 품질불량 / 수량오류 / RMA
  severity      VARCHAR(8),
  status        VARCHAR(12),
  root_cause    VARCHAR(120),
  linked_po_id  VARCHAR(14),
  linked_shipment_id VARCHAR(14)
);
