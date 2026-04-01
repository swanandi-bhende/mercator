import { useState } from 'react'
import toast, { Toaster } from 'react-hot-toast'

function App() {
  const [count, setCount] = useState(0)

  const handleNotification = () => {
    toast.success('Welcome to Mercator!')
  }

  return (
    <>
      <Toaster position="top-center" />
      <div className="app-container">
        <h1>🤖 Mercator AI Agent Marketplace</h1>
        <p>Algorand Micropayment Platform</p>
        
        <div className="card">
          <button 
            onClick={() => {
              setCount(count + 1)
              handleNotification()
            }}
          >
            Count is {count}
          </button>
          <p>
            Click to get started with Mercator
          </p>
        </div>
      </div>
    </>
  )
}

export default App
