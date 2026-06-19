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

  public linkOptions: SelectOption[] = []
  public selectedLink = ''
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
      this.linkOptions = lines.map((l, i) => ({value: String(i), label: l.label}))
      if (!this.linkOptions.find(o => o.value === this.selectedLink)) {
        this.selectedLink = this.linkOptions[0]?.value ?? ''
        if (this.selectedLink) this.controllerService.selectLink(this.selectedLink)
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

    return {
      station_edges: Object.fromEntries(
        Object.entries(stations.station_edges).map(([k, cells]) => [
          k, cells.map(mapCoord).filter((c): c is [number, number] => c !== null),
        ])
      ),
      station_gates: Object.fromEntries(
        Object.entries(stations.station_gates).map(([k, gates]) => [
          k,
          Object.fromEntries(
            Object.entries(gates).map(([gk, gate]) => [
              gk,
              {
                ...gate,
                pins: Object.fromEntries(
                  Object.entries(gate.pins)
                    .map(([pk, pin]) => {
                      const mapped = mapCoord(pin.node)
                      return mapped ? [pk, {...pin, node: mapped}] : null
                    })
                    .filter((e): e is [string, { name: string; node: [number, number] }] => e !== null)
                ),
              },
            ])
          ),
        ])
      ),
      station_stopping_points: Object.fromEntries(
        Object.entries(stations.station_stopping_points).map(([k, stationList]) => [
          k,
          stationList
            .map(stp => {
              const mapped = mapCoord(stp.node);
              return mapped ? {...stp, node: mapped} : null
            })
            .filter((s): s is { node: [number, number]; trackNumber: number; trackName: string } => s !== null),
        ])
      ),
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

  public onLinkChange() {
    this.controllerService.selectLink(this.selectedLink)
  }
}
