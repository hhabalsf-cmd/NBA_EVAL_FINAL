import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PersonalApp from './PersonalApp'
import ErrorBoundary from '../shared/components/ErrorBoundary'
import '../index.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60000, retry: false, refetchOnWindowFocus: false } } })
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ErrorBoundary><QueryClientProvider client={queryClient}><PersonalApp /></QueryClientProvider></ErrorBoundary></React.StrictMode>,
)
