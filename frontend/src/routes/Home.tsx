import { Link } from 'react-router-dom'

function Home() {
  return (
    <main>
      <h1>chat-app</h1>
      <p>Placeholder route — toolchain scaffold only.</p>
      teste
      <p>
        <Link to="/login">Entrar</Link>
      </p>
      <footer>
        <a href="https://www.flaticon.com/free-icons/msn" title="msn icons">
          Msn icons created by IconBaandar - Flaticon
        </a>
      </footer>
    </main>
  )
}

export default Home
