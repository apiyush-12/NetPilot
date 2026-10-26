import React, { useState } from 'react'
import {
  BrainCircuit,
  Play,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle
} from 'lucide-react'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { apiPostJson } from '../lib/api.js'
import { SectionHead, Label, Empty } from '../components/Chrome.jsx'

import './ai-operations.css'

export default function AIOperations({
  token,
  backendOnline,
  aiSession,
  setAiSession
}) {
  const{question, loading, result, error } = aiSession

  async function investigate(event) {
  event.preventDefault()

  const query = question.trim()

  if (query.length < 5 || loading) return

  setAiSession(prev => ({
    ...prev,
    loading: true,
    error: '',
    result: null
  }))

  try {
    const data = await apiPostJson(
      '/api/ai/analyze',
      token,
      { question: query }
    )

    setAiSession(prev => ({
      ...prev,
      result: data
    }))

  } catch (err) {
    setAiSession(prev => ({
      ...prev,
      error: err.message || 'Investigation failed'
    }))

  } finally {
    setAiSession(prev => ({
      ...prev,
      loading: false
    }))
  }
}

  const calls = result?.tool_calls || []

  return (
    <div className="page">

      <div className="page-head">
        <div className="eyebrow">
          INTELLIGENT NETWORK OPERATIONS / MCP
        </div>

        <h2>AI Operations</h2>

        <p>
          Investigate network failures using real NetPilot
          telemetry, incident history and read-only MCP tools.
        </p>
      </div>

      <div className="ai-ops-layout">

        <section className="panel ai-ops-main">

          <SectionHead
            title="NETWORK INVESTIGATION"
            detail="Groq-powered analysis using NetPilot MCP tools"
            right={<Label tone="good">READ ONLY</Label>}
          />

          <form
            className="ai-ops-form"
            onSubmit={investigate}
          >
            <label htmlFor="ai-question">
              OPERATOR QUESTION
            </label>

            <textarea
              id="ai-question"
              className="text-input ai-question"
              value={question}
              maxLength={1000}
              onChange={event =>
                setAiSession(prev => ({
                  ...prev,
                  question: event.target.value
                }))
              }
              disabled={loading}
              placeholder="Ask about connectivity, routing or incidents..."
            />

            <div className="ai-form-actions">
              <span>
                {question.length}/1000 characters
              </span>

              <button
                className="button button-accent"
                type="submit"
                disabled={
                  loading ||
                  !backendOnline ||
                  !token ||
                  question.trim().length < 5
                }
              >
                <Play size={13} />
                {loading
                  ? 'INVESTIGATING...'
                  : 'RUN INVESTIGATION'}
              </button>
            </div>

            {!token && (
              <p className="ai-form-hint">
                Unlock controls using your existing
                NetPilot token to enable AI analysis.
              </p>
            )}
          </form>

          {loading && (
            <div className="ai-feedback" role="status">
              <BrainCircuit size={17} />
              AI investigation running. MCP results
              will appear when analysis completes.
            </div>
          )}

          {error && (
            <div className="diagnostic-error" role="alert">
              <AlertTriangle size={15} />
              {error}
            </div>
          )}

          {result ? (
            <div className="ai-result">
              <div className="ai-result-heading">
                <BrainCircuit size={17} />
                <strong>INVESTIGATION RESULT</strong>
                <Label tone="good">COMPLETED</Label>
              </div>

              <div className="ai-model-info">
                PROVIDER: {result.provider}
                {'  /  '}
                MODEL: {result.model}
              </div>

              {/* G3: Output Guardrail Results */}
              {result.guardrails && (
                <div className="ai-security-note">
                  <ShieldCheck size={16} />

                  <div>
                    <strong>
                      OUTPUT GUARDRAIL: {
                        result.guardrails.status?.toUpperCase()
                      }
                    </strong>

                    <div>
                      Output Format: {
                        result.guardrails.checks?.output_format
                      }
                    </div>

                    <div>
                      Secret Scan: {
                        result.guardrails.checks?.secret_scan
                      }
                    </div>

                    <div>
                      Tool Allowlist: {
                        result.guardrails.checks?.tool_allowlist
                      }
                    </div>

                    {(result.guardrails.warnings || []).map(
                      (warning, index) => (
                        <p key={index}>
                          Warning: {warning}
                        </p>
                      )
                    )}

                    <small>
                      Audit ID: {result.audit_id}
                    </small>
                  </div>
                </div>
              )}

              {/* Existing AI Analysis */}
              <div className="ai-answer-content">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  skipHtml
                >
                  {String(result.answer || '')}
                </ReactMarkdown>
              </div>
            </div>
          ) : !loading && !error && (
            <Empty
              text="Submit a question to begin an AI investigation."
            />
          )}
        </section>

        <section className="panel ai-ops-trace">

          <SectionHead
            title="MCP EXECUTION TRACE"
            detail="Tools selected by the AI agent"
            right={<Label>{calls.length} CALLS</Label>}
          />

          {calls.length ? (
            <div className="ai-tool-list">
              {calls.map((call, index) => (
                <div
                  className="ai-tool-row"
                  key={`${call.tool}-${index}`}
                >
                  <CheckCircle2
                    size={15}
                    color="#65d7b1"
                  />

                  <div>
                    <strong>{call.tool}</strong>
                    <span>
                      {call.status}
                      {' · '}
                      {call.duration_ms ?? '-'} ms
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty text="No MCP tool calls recorded yet." />
          )}

          <div className="ai-security-note">
            <ShieldCheck size={16} />
            <span>
              MCP tools are read-only. This agent cannot
              execute Docker commands or modify routes.
              Tool completion does not independently
              guarantee diagnostic success.
            </span>
          </div>
        </section>

      </div>
    </div>
  )
}