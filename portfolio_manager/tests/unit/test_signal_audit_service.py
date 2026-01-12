"""
Tests for Signal Audit Service

Tests:
- SignalAuditRecord creation
- ValidationResultData conversion
- SizingCalculationData conversion
- Database operations (mocked)
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from core.signal_audit_service import (
    SignalAuditService,
    SignalOutcome,
    SignalAuditRecord,
    ValidationResultData,
    SizingCalculationData,
    RiskAssessmentData,
    OrderExecutionData
)


class TestSignalOutcome:
    """Test SignalOutcome enum."""

    def test_all_outcomes_defined(self):
        """Verify all expected outcomes exist."""
        expected = [
            'PROCESSED',
            'REJECTED_VALIDATION',
            'REJECTED_RISK',
            'REJECTED_DUPLICATE',
            'REJECTED_MARKET',
            'REJECTED_MANUAL',
            'FAILED_ORDER',
            'PARTIAL_FILL'
        ]
        actual = [o.value for o in SignalOutcome]
        assert set(expected) == set(actual)

    def test_outcome_values(self):
        """Verify outcome enum values match database constraints."""
        assert SignalOutcome.PROCESSED.value == 'PROCESSED'
        assert SignalOutcome.REJECTED_VALIDATION.value == 'REJECTED_VALIDATION'


class TestValidationResultData:
    """Test ValidationResultData dataclass."""

    def test_basic_creation(self):
        """Test basic ValidationResultData creation."""
        data = ValidationResultData(
            is_valid=True,
            severity="NORMAL",
            signal_age_seconds=1.5
        )
        assert data.is_valid is True
        assert data.severity == "NORMAL"
        assert data.signal_age_seconds == 1.5

    def test_to_dict_excludes_none(self):
        """Test to_dict excludes None values."""
        data = ValidationResultData(
            is_valid=True,
            severity="NORMAL"
        )
        result = data.to_dict()
        assert 'is_valid' in result
        assert 'severity' in result
        # None fields should be excluded
        assert result.get('signal_age_seconds') is None or 'signal_age_seconds' not in result or result['signal_age_seconds'] is None

    def test_full_creation(self):
        """Test full ValidationResultData with all fields."""
        data = ValidationResultData(
            is_valid=False,
            severity="REJECTED",
            signal_age_seconds=300.0,
            divergence_pct=0.025,
            risk_increase_pct=0.15,
            direction="unfavorable",
            reason="divergence_too_high"
        )
        result = data.to_dict()
        assert result['is_valid'] is False
        assert result['divergence_pct'] == 0.025


class TestSizingCalculationData:
    """Test SizingCalculationData dataclass."""

    def test_basic_creation(self):
        """Test basic SizingCalculationData creation."""
        data = SizingCalculationData(
            method="TOM_BASSO",
            equity_high=5000000,
            risk_percent=1.0,
            final_lots=3,
            limiter="RISK"
        )
        assert data.method == "TOM_BASSO"
        assert data.equity_high == 5000000

    def test_to_dict_structure(self):
        """Test to_dict returns correct structure."""
        data = SizingCalculationData(
            method="TOM_BASSO",
            equity_high=5000000,
            risk_percent=1.0,
            stop_distance=500.0,
            lot_size=30,
            point_value=30.0,
            risk_amount=50000,
            raw_lots=3.33,
            final_lots=3,
            limiter="RISK"
        )
        result = data.to_dict()

        assert result['method'] == "TOM_BASSO"
        assert 'inputs' in result
        assert 'calculation' in result
        assert result['inputs']['equity_high'] == 5000000
        assert result['calculation']['final_lots'] == 3


class TestRiskAssessmentData:
    """Test RiskAssessmentData dataclass."""

    def test_basic_creation(self):
        """Test basic RiskAssessmentData creation."""
        data = RiskAssessmentData(
            margin_available=1500000,
            margin_required=390000,
            checks_passed=['MARGIN', 'MAX_POSITIONS']
        )
        assert data.margin_available == 1500000
        assert 'MARGIN' in data.checks_passed

    def test_to_dict(self):
        """Test to_dict conversion."""
        data = RiskAssessmentData(
            pre_trade_risk_pct=2.5,
            post_trade_risk_pct=3.5,
            margin_available=1500000,
            margin_required=390000,
            checks_passed=['MARGIN']
        )
        result = data.to_dict()
        assert result['pre_trade_risk_pct'] == 2.5
        assert result['margin_required'] == 390000


class TestOrderExecutionData:
    """Test OrderExecutionData dataclass."""

    def test_basic_creation(self):
        """Test basic OrderExecutionData creation."""
        data = OrderExecutionData(
            order_id="ORD_123",
            execution_status="SUCCESS",
            fill_price=52000.0,
            slippage_pct=0.001
        )
        assert data.order_id == "ORD_123"
        assert data.execution_status == "SUCCESS"

    def test_synthetic_with_legs(self):
        """Test OrderExecutionData with synthetic futures legs."""
        data = OrderExecutionData(
            order_id="SYNTH_123",
            order_type="SYNTHETIC_FUTURES",
            execution_status="SUCCESS",
            fill_price=52100.0,
            legs=[
                {"leg": "PE", "fill_price": 450.0},
                {"leg": "CE", "fill_price": 350.0}
            ]
        )
        assert len(data.legs) == 2
        assert data.legs[0]['leg'] == "PE"


class TestSignalAuditRecord:
    """Test SignalAuditRecord dataclass."""

    def test_basic_creation(self):
        """Test basic record creation."""
        record = SignalAuditRecord(
            signal_fingerprint="test_fp_123",
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="LONG",
            signal_timestamp=datetime.now(),
            received_at=datetime.now(),
            outcome=SignalOutcome.PROCESSED,
            outcome_reason="executed_successfully"
        )
        assert record.signal_fingerprint == "test_fp_123"
        assert record.instrument == "BANK_NIFTY"
        assert record.outcome == SignalOutcome.PROCESSED


class TestSignalAuditService:
    """Test SignalAuditService (with mocked database)."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager with transaction support."""
        from contextlib import contextmanager

        db_manager = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()

        # Setup cursor context manager
        cursor_cm = MagicMock()
        cursor_cm.__enter__ = MagicMock(return_value=cursor)
        cursor_cm.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor_cm

        # Setup transaction context manager
        @contextmanager
        def mock_transaction():
            yield conn

        db_manager.transaction = mock_transaction

        return db_manager, conn, cursor

    def test_service_initialization(self, mock_db_manager):
        """Test service initialization."""
        db_manager, _, _ = mock_db_manager
        service = SignalAuditService(db_manager)
        assert service is not None

    def test_create_audit_record(self, mock_db_manager):
        """Test creating audit record."""
        db_manager, conn, cursor = mock_db_manager
        cursor.fetchone.return_value = (1,)  # Return ID

        service = SignalAuditService(db_manager)

        record = SignalAuditRecord(
            signal_fingerprint="test_fp",
            instrument="GOLD_MINI",
            signal_type="BASE_ENTRY",
            position="LONG",
            signal_timestamp=datetime.now(),
            received_at=datetime.now(),
            outcome=SignalOutcome.PROCESSED
        )

        result = service.create_audit_record(record)

        assert result == 1
        assert cursor.execute.called
        assert conn.commit.called

    def test_update_outcome(self, mock_db_manager):
        """Test updating audit record outcome."""
        db_manager, conn, cursor = mock_db_manager
        cursor.rowcount = 1

        service = SignalAuditService(db_manager)

        result = service.update_outcome(
            audit_id=1,
            outcome=SignalOutcome.REJECTED_VALIDATION,
            outcome_reason="divergence_too_high"
        )

        assert result is True
        assert cursor.execute.called


class TestSignalValidatorAuditIntegration:
    """Test SignalValidator audit integration methods."""

    def test_condition_result_to_dict(self):
        """Test ConditionValidationResult.to_dict()."""
        from core.signal_validator import (
            ConditionValidationResult,
            ValidationSeverity
        )

        result = ConditionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.NORMAL,
            reason="conditions_met",
            signal_age_seconds=2.5
        )

        data = result.to_dict()

        assert data['is_valid'] is True
        assert data['severity'] == 'normal'
        assert data['signal_age_seconds'] == 2.5

    def test_execution_result_to_dict(self):
        """Test ExecutionValidationResult.to_dict()."""
        from core.signal_validator import ExecutionValidationResult

        result = ExecutionValidationResult(
            is_valid=True,
            reason="execution_validated",
            divergence_pct=0.008,
            risk_increase_pct=0.02,
            direction="favorable"
        )

        data = result.to_dict()

        assert data['is_valid'] is True
        assert data['divergence_pct'] == 0.008
        assert data['direction'] == "favorable"

    def test_create_validation_result_for_audit(self):
        """Test combined validation result creation."""
        from core.signal_validator import (
            SignalValidator,
            ConditionValidationResult,
            ExecutionValidationResult,
            ValidationSeverity
        )

        condition = ConditionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.NORMAL
        )
        execution = ExecutionValidationResult(
            is_valid=True,
            divergence_pct=0.005
        )

        result = SignalValidator.create_validation_result_for_audit(
            condition, execution
        )

        assert 'condition_validation' in result
        assert 'execution_validation' in result
        assert result['condition_validation']['is_valid'] is True


class TestPositionSizerAuditIntegration:
    """Test PositionSizer audit integration methods."""

    def test_create_sizing_data_for_audit_base_entry(self):
        """Test sizing data creation for base entry."""
        from core.position_sizer import TomBassoPositionSizer
        from core.models import Signal, SignalType, InstrumentConfig, TomBassoConstraints
        from datetime import datetime

        config = InstrumentConfig(
            name='TEST',
            instrument_type='FUTURES',
            lot_size=30,
            point_value=30.0,
            margin_per_lot=130000,
            initial_risk_percent=1.0,
            initial_vol_percent=2.0,
            ongoing_risk_percent=2.0,
            ongoing_vol_percent=4.0
        )

        sizer = TomBassoPositionSizer(config)

        signal = Signal(
            timestamp=datetime.now(),
            instrument='BANK_NIFTY',
            signal_type=SignalType.BASE_ENTRY,
            position='LONG',
            price=52000.0,
            stop=51500.0,
            suggested_lots=3,
            atr=200.0,
            er=0.85,
            supertrend=51600.0
        )

        constraints = TomBassoConstraints(
            lot_r=3.5, lot_v=4.2, lot_m=5.0,
            final_lots=3, limiter='risk'
        )

        result = sizer.create_sizing_data_for_audit(
            signal=signal,
            equity=5000000,
            available_margin=1500000,
            constraints=constraints
        )

        assert result['method'] == 'TOM_BASSO'
        assert 'inputs' in result
        assert 'calculation' in result
        assert result['inputs']['equity_high'] == 5000000
        assert result['calculation']['final_lots'] == 3
        assert result['limiter'] == 'RISK'
