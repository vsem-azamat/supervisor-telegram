import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import '../styles/markdown.css'

interface MarkdownContentProps {
  content: string
  className?: string
}

export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, className }) => {
  return (
    <div className={`markdown-content ${className || ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
      components={{
        // Custom styles for markdown elements
        h1: ({ children }) => (
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.75rem', marginTop: '1rem' }}>
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem', marginTop: '0.75rem' }}>
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem', marginTop: '0.5rem' }}>
            {children}
          </h3>
        ),
        p: ({ children }) => (
          <p style={{ marginBottom: '0.75rem', lineHeight: 1.6 }}>{children}</p>
        ),
        ul: ({ children }) => (
          <ul style={{ marginBottom: '0.75rem', paddingLeft: '1.5rem', lineHeight: 1.6 }}>{children}</ul>
        ),
        ol: ({ children }) => (
          <ol style={{ marginBottom: '0.75rem', paddingLeft: '1.5rem', lineHeight: 1.6 }}>{children}</ol>
        ),
        li: ({ children }) => (
          <li style={{ marginBottom: '0.25rem' }}>{children}</li>
        ),
        code: ({ className, children }) => {
          const isInline = !className
          return isInline ? (
            <code
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.1)',
                padding: '0.125rem 0.25rem',
                borderRadius: '3px',
                fontSize: '0.875rem',
                fontFamily: 'monospace'
              }}
            >
              {children}
            </code>
          ) : (
            <code className={className}>{children}</code>
          )
        },
        pre: ({ children }) => (
          <pre
            style={{
              backgroundColor: '#0d1117',
              padding: '1rem',
              borderRadius: '6px',
              overflow: 'auto',
              marginBottom: '0.75rem',
              fontSize: '0.875rem'
            }}
          >
            {children}
          </pre>
        ),
        blockquote: ({ children }) => (
          <blockquote
            style={{
              borderLeft: '4px solid var(--mantine-color-gray-4)',
              paddingLeft: '1rem',
              marginLeft: 0,
              marginBottom: '0.75rem',
              fontStyle: 'italic',
              color: 'var(--mantine-color-gray-7)'
            }}
          >
            {children}
          </blockquote>
        ),
        table: ({ children }) => (
          <div style={{ overflowX: 'auto', marginBottom: '0.75rem' }}>
            <table
              style={{
                borderCollapse: 'collapse',
                width: '100%',
                fontSize: '0.875rem'
              }}
            >
              {children}
            </table>
          </div>
        ),
        th: ({ children }) => (
          <th
            style={{
              border: '1px solid var(--mantine-color-gray-4)',
              padding: '0.5rem',
              backgroundColor: 'var(--mantine-color-gray-1)',
              fontWeight: 600,
              textAlign: 'left'
            }}
          >
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td
            style={{
              border: '1px solid var(--mantine-color-gray-4)',
              padding: '0.5rem'
            }}
          >
            {children}
          </td>
        ),
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: 'var(--mantine-color-blue-6)',
              textDecoration: 'none',
              borderBottom: '1px solid var(--mantine-color-blue-6)'
            }}
          >
            {children}
          </a>
        ),
        hr: () => (
          <hr
            style={{
              border: 'none',
              borderTop: '1px solid var(--mantine-color-gray-4)',
              margin: '1rem 0'
            }}
          />
        )
      }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
