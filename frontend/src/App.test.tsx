import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the harness hello world', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /book illustration studio/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/hello world/i)).toBeInTheDocument()
  })
})
