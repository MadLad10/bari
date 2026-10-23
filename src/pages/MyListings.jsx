import { Navigate } from "react-router-dom";

export default function MyListings() {
  return <Navigate to="/owner?tab=listings" replace />;
}
