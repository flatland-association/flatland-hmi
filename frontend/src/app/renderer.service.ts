import { Injectable } from '@angular/core'
import { Agent, StationsResponse, Transitions } from './data.service'

export interface MapCell {
  ground: string
  stationBuilding?: string
  station?: boolean
  outerConnectionPoint?: boolean
  outerConnectionPointLabel?: string
  trackNumber?: number
  trackName?: string
}

const BACKGROUND_CLASSES_WEIGHT = {
  grass: 8,
  water: 1,
  trees: 20,
  forest: 16,
  mountain: 6,
}

const TRANSITION_CLASSES_MAP = Object.fromEntries(
  [
    'WE',
    'WW EE NN SS',
    'WW EE',
    'EN SW',
    'WN SE',
    'ES NW',
    'NE WS',
    'NN SS',
    'NN SS EE WW ES NW SE WN',
    'EE WW EN SW',
    'EE WW SE WN',
    'EE WW ES NW',
    'EE WW NE WS',
    'NN SS EE WW NW ES',
    'NE NW ES WS',
    'NN SS EN SW',
    'NN SS SE WN',
    'NN SS NW ES',
    'NN SS NE WS',
  ].flatMap((transition) => {
    if (transition === '') {
      return [[0, []]]
    }
    const binaryList = Array(16).fill('0')
    for (const dir of transition.split(' ')) {
      const iDirIn = 'NESW'.indexOf(dir[0])
      const iDirOut = 'NESW'.indexOf(dir[1])
      const iTrans = 4 * iDirIn + iDirOut
      binaryList[iTrans] = '1'
    }
    const bitmap = parseInt(binaryList.join(''), 2)
    return [0, 1, 2, 3].map((direction) => [
      rotateTransition(bitmap, direction * 90),
      [
        `rotation_${direction * 90}`,
        'track',
        `transition_${transition.split(' ').join('_').toLocaleLowerCase()}`,
      ],
    ])
  }),
)

function rotateTransition(transition: number, rotation: number): number {
  const rotationSteps = (rotation / 90) % 4
  if (rotationSteps === 0) return transition

  let value = transition
  for (let i = 0; i < 4; i++) {
    const mask = 0xf << (i * 4)
    const rowBits = (value & mask) >> (i * 4)
    const rotatedBits =
      ((rowBits << (4 - rotationSteps)) | (rowBits >> rotationSteps)) & 0xf
    value = (value & ~mask) | (rotatedBits << (i * 4))
  }

  const lowerMask = (1 << (rotationSteps * 4)) - 1
  const lowerBits = value & lowerMask
  const upperBits = value >> (rotationSteps * 4)
  value = (lowerBits << ((4 - rotationSteps) * 4)) | upperBits

  return value
}

function getBackgroundClasses() {
  const sum = Object.values(BACKGROUND_CLASSES_WEIGHT).reduce(
    (acc, weight) => acc + weight,
    0,
  )
  const random = Math.floor(Math.random() * sum)
  let lastWeight = 0
  for (const [key, weight] of Object.entries(BACKGROUND_CLASSES_WEIGHT)) {
    lastWeight += weight
    if (random < lastWeight) {
      return ['bkgnd', `bkgnd_${key}`]
    }
  }
  return ''
}

@Injectable({
  providedIn: 'root',
})
export class RendererService {
  constructor() {}

  public getMapClasses(transition: number): string {
    return (TRANSITION_CLASSES_MAP[transition] || getBackgroundClasses()).join(
      ' ',
    )
  }

  public getTargetClasses(transition: number): string {
    return TRANSITION_CLASSES_MAP[transition]?.[0] ?? 'error'
  }

  public getAgentClasses(agent: Agent | undefined): string {
    return agent ? `handle_${agent.handle} direction_${agent.direction} ${agent.malfunction > 0 ? 'malfunction' : ''}` : ''
  }

  public renderMap(transitions: Transitions, agents: Array<Agent>, stations: StationsResponse = {
    station_edges: {},
    station_gates: {},
    inter_city_lines: [],
    station_stopping_points: {},
    outer_connection_point_labels: {}
  }) {

    const stoppingPointCoords = new Map<number, Map<number, { rotationClass: string; trackNumber: number; trackName: string }>>()
    for (const stoppingPoints of Object.values(stations.station_stopping_points)) {
      stoppingPoints.forEach(stp => {
        const [r, c] = stp.node
        if (!stoppingPointCoords.has(r)) stoppingPointCoords.set(r, new Map())
        stoppingPointCoords.get(r)!.set(c, {rotationClass: 'rotation_270', trackNumber: stp.trackNumber, trackName: stp.trackName})
      })
    }

    const stationEdgeCoords = new Map<number, Set<number>>()
    for (const [r, c] of Object.values(stations.station_edges).flat()) {
      if (!stationEdgeCoords.has(r)) stationEdgeCoords.set(r, new Set())
      stationEdgeCoords.get(r)!.add(c)
    }

    const ocpCoords = new Map<number, Set<number>>()
    for (const gates of Object.values(stations.station_gates)) {
      for (const gate of gates) {
        for (const pin of Object.values(gate.pins)) {
          const [r, c] = pin.node
          if (!ocpCoords.has(r)) ocpCoords.set(r, new Set())
          ocpCoords.get(r)!.add(c)
        }
      }
    }

    const ocpLabelCoords = new Map<number, Map<number, string>>()
    for (const [key, label] of Object.entries(stations.outer_connection_point_labels)) {
      const [r, c] = key.split(',').map(Number)
      if (!ocpLabelCoords.has(r)) ocpLabelCoords.set(r, new Map())
      ocpLabelCoords.get(r)!.set(c, label)
    }

    const mapClasses: Array<Array<MapCell>> = []
    for (let i = 0; i < transitions.length; i++) {
      const row = transitions[i]
      const mapRow: Array<MapCell> = []
      for (let j = 0; j < row.length; j++) {
        const cell = row[j]
        const ground = this.getMapClasses(cell)
        const stoppingPoint = stoppingPointCoords.get(i)?.get(j)

        // Bahnhof.svg
        const stationBuilding = stoppingPoint?.rotationClass
        const trackNumber = stoppingPoint?.trackNumber
        const trackName = stoppingPoint?.trackName

        const outerConnectionPoint = ocpCoords.get(i)?.has(j) ? true : undefined
        const outerConnectionPointLabel = outerConnectionPoint ? ocpLabelCoords.get(i)?.get(j) : undefined
        let station = stationEdgeCoords.get(i)?.has(j) ? true : undefined
        // either station or outerConnectionPoint
        if (outerConnectionPoint) {
          station = undefined
        }

        mapRow.push({ground, stationBuilding, station, outerConnectionPoint, outerConnectionPointLabel, trackNumber, trackName})
      }
      mapClasses.push(mapRow)
    }
    return mapClasses
  }
}
