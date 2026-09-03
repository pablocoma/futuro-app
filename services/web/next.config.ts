import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `standalone` empaqueta el servidor con solo las dependencias que usa,
  // así la imagen de producción no lleva node_modules completo.
  output: "standalone",
};

export default nextConfig;
