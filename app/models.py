"""
Modelos SQLAlchemy para o banco de dados.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Execucao(Base):
    __tablename__ = "execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_execucao: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    numero_rpi: Mapped[str | None] = mapped_column(String(20))
    data_rpi: Mapped[str | None] = mapped_column(String(20))
    total_carteira: Mapped[int | None] = mapped_column(Integer)
    total_rpi: Mapped[int | None] = mapped_column(Integer)
    total_rpi_oposicao: Mapped[int | None] = mapped_column(Integer)
    total_rpi_pan: Mapped[int | None] = mapped_column(Integer)
    despachos_selecionados: Mapped[str | None] = mapped_column(Text)  # JSON
    alertas_alta: Mapped[int | None] = mapped_column(Integer)
    alertas_media: Mapped[int | None] = mapped_column(Integer)
    alertas_baixa: Mapped[int | None] = mapped_column(Integer)
    alertas_total: Mapped[int | None] = mapped_column(Integer)
    alertas_oposicao: Mapped[int | None] = mapped_column(Integer)
    alertas_pan: Mapped[int | None] = mapped_column(Integer)
    tempo_execucao_seg: Mapped[float | None] = mapped_column(Float)
    custo_ia_usd: Mapped[float | None] = mapped_column(Float)
    arquivo_carteira: Mapped[str | None] = mapped_column(String(500))
    arquivo_rpi: Mapped[str | None] = mapped_column(String(500))
    arquivo_resultado: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="em_andamento")
    erro_msg: Mapped[str | None] = mapped_column(Text)

    # Progresso do pipeline (armazenado como JSON)
    progresso: Mapped[str | None] = mapped_column(Text)

    resultados: Mapped[list[Resultado]] = relationship(
        "Resultado", back_populates="execucao", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_execucoes_data", "data_execucao"),
    )


class Resultado(Base):
    __tablename__ = "resultados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execucao_id: Mapped[int] = mapped_column(Integer, ForeignKey("execucoes.id", ondelete="CASCADE"))
    tipo_acao: Mapped[str | None] = mapped_column(String(20))   # OPOSICAO | PAN
    despacho_codigo: Mapped[str | None] = mapped_column(String(20))
    despacho_nome: Mapped[str | None] = mapped_column(String(200))
    marca_base: Mapped[str | None] = mapped_column(String(500))
    ncl_base: Mapped[int | None] = mapped_column(Integer)
    spec_base: Mapped[str | None] = mapped_column(Text)
    marca_rpi: Mapped[str | None] = mapped_column(String(500))
    ncl_rpi: Mapped[int | None] = mapped_column(Integer)
    spec_rpi: Mapped[str | None] = mapped_column(Text)
    processo_rpi: Mapped[str | None] = mapped_column(String(50))
    titular_rpi: Mapped[str | None] = mapped_column(String(500))
    classificacao: Mapped[str | None] = mapped_column(String(20))   # ALTA|MEDIA|BAIXA|NENHUMA
    score_final: Mapped[float | None] = mapped_column(Float)
    score_nome: Mapped[float | None] = mapped_column(Float)
    score_fonetico: Mapped[float | None] = mapped_column(Float)
    score_spec: Mapped[float | None] = mapped_column(Float)
    score_nucleo: Mapped[float | None] = mapped_column(Float)
    score_ia: Mapped[float | None] = mapped_column(Float)
    camada_deteccao: Mapped[int | None] = mapped_column(Integer)
    justificativa_ia: Mapped[str | None] = mapped_column(Text)
    nucleo_base: Mapped[str | None] = mapped_column(String(500))
    nucleo_rpi: Mapped[str | None] = mapped_column(String(500))
    classes_colidem: Mapped[bool | None] = mapped_column(Boolean)
    is_sigla: Mapped[bool | None] = mapped_column(Boolean)
    is_desgastado: Mapped[bool | None] = mapped_column(Boolean)
    aspecto_grafico: Mapped[float | None] = mapped_column(Float)
    aspecto_fonetico: Mapped[float | None] = mapped_column(Float)
    aspecto_ideologico: Mapped[float | None] = mapped_column(Float)
    afinidade_mercadologica: Mapped[float | None] = mapped_column(Float)

    execucao: Mapped[Execucao] = relationship("Execucao", back_populates="resultados")

    __table_args__ = (
        Index("idx_resultados_execucao", "execucao_id"),
        Index("idx_resultados_classificacao", "execucao_id", "classificacao"),
        Index("idx_resultados_tipo_acao", "execucao_id", "tipo_acao"),
    )
