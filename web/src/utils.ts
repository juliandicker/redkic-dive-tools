const RHO_O2 = 32 / 22.4
const RHO_N2 = 28 / 22.4
const RHO_HE =  4 / 22.4

export function surfaceDensity(o2: number, he: number): number {
  const fO2 = o2 / 100, fHe = he / 100, fN2 = Math.max(0, 1 - fO2 - fHe)
  return fO2 * RHO_O2 + fN2 * RHO_N2 + fHe * RHO_HE
}

export function densityLimitDepth(o2: number, he: number, limitGl = 5.2): number {
  const rho0 = surfaceDensity(o2, he)
  if (rho0 <= 0) return 999
  return Math.max(0, Math.floor((limitGl / rho0 - 1) * 10))
}

export function bestMix(
  depth: number, setpoint: number, densityLimitGl: number
): { o2: number; he: number } {
  const amb = depth / 10 + 1
  const fO2 = Math.min(0.21, setpoint / amb)
  const densLimSurf = densityLimitGl / amb
  let fHe = (densLimSurf - RHO_N2 - fO2 * (RHO_O2 - RHO_N2)) / (RHO_HE - RHO_N2)
  fHe = Math.max(0, Math.min(1 - fO2, fHe))
  const heRounded = Math.ceil(fHe * 20) * 5
  let o2Rounded = Math.round(fO2 * 100)
  if (o2Rounded + heRounded > 100) o2Rounded = 100 - heRounded
  return { o2: o2Rounded, he: heRounded }
}

export function bailoutAutoMod(o2: number): number {
  if (o2 <= 0) return 150
  const fo2 = o2 / 100
  const depthAt14 = (1.4 / fo2 - 1.013) * 10
  if (depthAt14 <= 10) {
    const depthAt16 = (1.6 / fo2 - 1.013) * 10
    return Math.max(3, Math.round(depthAt16 / 3) * 3)
  }
  return Math.max(3, Math.floor(depthAt14 / 3) * 3)
}

export function gasName(o2: number, he: number): string {
  if (o2 === 100) return 'O₂'
  if (he === 0) return o2 === 21 ? 'Air' : `N${o2}`
  return `Tx${o2}/${he}`
}

export function gasNameCompact(o2: number, he: number): string {
  if (o2 === 100) return 'O₂'
  if (he === 0) return o2 === 21 ? 'Air' : `${o2}%`
  return `${o2}/${he}`
}
