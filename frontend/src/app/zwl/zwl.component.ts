import {Component, OnInit} from '@angular/core'
import {StateService} from '../state.service'
import {MapCell, RendererService} from '../renderer.service'
import {Agent, StationsResponse} from '../data.service'
import {FormsModule} from '@angular/forms'
import {ControllerService} from '../controller.service'
import {combineLatest} from 'rxjs'

interface SelectOption {
  value: string
  label: string
}

@Component({
  selector: 'app-zwl',
  imports: [FormsModule],
  templateUrl: './zwl.component.html',
  styleUrl: './zwl.component.scss',
})
export class ZwlComponent implements OnInit {
  public mapClasses: Array<Array<MapCell>> = []
  public agents: Array<Agent> = []

  public lineOptions: SelectOption[] = []
  public selectedLine = ''
  public mapping: Map<number, Map<number, [number, number]>> = new Map()
  public reverseMapping: Map<number, Map<number, [number, number]>> = new Map()

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
    public controllerService: ControllerService,
  ) {
  }

  ngOnInit() {
    this.stateService.getLines().subscribe(lines => {
      this.lineOptions = lines.map((l, i) => ({value: String(i), label: l.label}))
      if (!this.lineOptions.find(o => o.value === this.selectedLine)) {
        this.selectedLine = this.lineOptions[0]?.value ?? ''
        if (this.selectedLine) this.controllerService.selectLine(this.selectedLine)
      }
    })
    combineLatest([
      this.stateService.getLineTransitions(),
      this.stateService.getStations(),
    ]).subscribe(([data, stations]) => {
      this.setMapping(data.mapping)
      this.mapClasses = this.rendererService.renderMap(data.grid, [], this.transformStationsForZwl(stations))
    })
    this.stateService.getAgents().subscribe(agents => {
      this.agents = agents
    })
  }

  private transformStationsForZwl(stations: StationsResponse): StationsResponse {
    const mapCoord = ([r, c]: [number, number]): [number, number] | null =>
      this.mapping.get(r)?.get(c) ?? null

    const transformKey = (key: string): string | null => {
      const [r, c] = key.split(',').map(Number)
      const mapped = mapCoord([r, c])
      return mapped ? `${mapped[0]},${mapped[1]}` : null
    }

    const transformLabels = (labels: Record<string, string>): Record<string, string> =>
      Object.fromEntries(
        Object.entries(labels)
          .map(([k, v]) => {
            const nk = transformKey(k);
            return nk ? [nk, v] : null
          })
          .filter((e): e is [string, string] => e !== null)
      )

    return {
      city_cells: Object.fromEntries(
        Object.entries(stations.city_cells).map(([k, cells]) => [
          k, cells.map(mapCoord).filter((c): c is [number, number] => c !== null),
        ])
      ),
      outer_connection_points_per_city: Object.fromEntries(
        Object.entries(stations.outer_connection_points_per_city).map(([k, pins]) => [
          k, (pins as [number, number][]).map(mapCoord).filter((c): c is [number, number] => c !== null),
        ])
      ),
      inter_city_lines: [],
      train_stations: Object.fromEntries(
        Object.entries(stations.train_stations).map(([k, stationList]) => [
          k,
          stationList
            .map(([[r, c], trackIdx]): [[number, number], number] | null => {
              const mapped = mapCoord([r, c])
              return mapped ? [mapped, trackIdx] : null
            })
            .filter((s): s is [[number, number], number] => s !== null),
        ])
      ),
      train_station_labels: transformLabels(stations.train_station_labels),
      outer_connection_point_labels: transformLabels(stations.outer_connection_point_labels),
    }
  }

  private setMapping(mappingArray: Array<[[number, number], [number, number]]>) {
    this.mapping = new Map()
    this.reverseMapping = new Map()
    for (const [[r, c], [mr, mc]] of mappingArray) {
      if (!this.mapping.has(r)) this.mapping.set(r, new Map())
      this.mapping.get(r)!.set(c, [mr, mc])
      if (!this.reverseMapping.has(mr)) this.reverseMapping.set(mr, new Map())
      this.reverseMapping.get(mr)!.set(mc, [r, c])
    }
  }

  public getOriginalPosition(zwlRow: number, zwlCol: number): [number, number] | null {
    return this.reverseMapping.get(zwlRow)?.get(zwlCol) ?? null
  }

  public getZwlPosition(x: number, y: number): [number, number] | null {
    return this.mapping.get(x)?.get(y) ?? null
  }

  public onLineChange() {
    this.controllerService.selectLine(this.selectedLine)
  }
}
