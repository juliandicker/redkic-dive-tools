export default function LoadingSpinner({ message = 'Calculating…' }: { message?: string }) {
  return (
    <div className="loading-spinner text-center py-3">
      <div className="spinner-border" />
      <div className="text-muted mt-1">{message}</div>
    </div>
  )
}
